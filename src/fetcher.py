import os
import re
import html
import requests
from typing import List, Dict, Optional, Set
from .config import TMP_PDF_DIR

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://stock.naver.com/research/daily",
}

LIST_API = "https://m.stock.naver.com/api/research/daily"
DETAIL_API = "https://m.stock.naver.com/api/research/daily/{research_id}"


def _clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def fetch_daily_list(pages: int = 2) -> List[Dict]:
    """네이버 증권 데일리 리서치 목록을 최대 pages 페이지까지 가져온다."""
    all_items: List[Dict] = []
    seen_ids: Set[int] = set()
    for page in range(1, pages + 1):
        try:
            resp = requests.get(f"{LIST_API}?page={page}&pageSize=20", headers=HEADERS, timeout=15)
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            for it in items:
                rid = it.get("researchId")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_items.append(it)
        except Exception as e:
            print(f"[수집] 목록 {page}페이지 조회 실패: {e}")
            break
    return all_items


def fetch_report_details(items: List[Dict], limit: int = 18) -> List[Dict]:
    """목록 항목들에 대해 상세 API(PDF URL, 본문 스니펫)를 조회한다."""
    reports = []
    for it in items[:limit]:
        rid = it.get("researchId")
        if not rid:
            continue
        try:
            d_resp = requests.get(DETAIL_API.format(research_id=rid), headers=HEADERS, timeout=15)
            d_resp.raise_for_status()
            detail = d_resp.json().get("researchContent", {})
        except Exception as e:
            print(f"[수집] 상세 조회 실패 (id={rid}): {e}")
            continue

        attach_url = detail.get("attachUrl", "")
        if not attach_url:
            continue

        reports.append({
            "research_id": rid,
            "title": detail.get("title") or it.get("title", ""),
            "broker": detail.get("brokerName") or it.get("brokerName", ""),
            "write_date": detail.get("writeDate") or it.get("writeDate", ""),
            "read_count": int(detail.get("readCount") or it.get("readCount") or 0),
            "pdf_url": attach_url,
            "naver_url": it.get("endUrl", f"https://m.stock.naver.com/research/daily/{rid}"),
            "snippet": _clean_html(detail.get("content", "")),
        })

    return reports


def fetch_smart_candidates(
    today_str: str,
    sent_ids: Set[int],
    min_today_count: int = 5,
    allow_fallback: bool = True,
    limit: int = 18,
) -> Dict:
    """
    업로드 텀과 휴장일을 고려한 스마트 후보 수집:
    1) 오늘 날짜(today_str) 미발송 리포트가 min_today_count 이상이면 오늘 리포트만 후보로 반환
    2) 오늘 리포트가 min_today_count 미만이고 allow_fallback=False(1차 조기 체크)이면 대기 신호 반환
    3) allow_fallback=True(최종 체크)인데 오늘 리포트가 부족하면, 최근 미발송 리포트를 합쳐 '그 다음 베스트' 후보 반환
    """
    raw_items = fetch_daily_list(pages=2)
    if not raw_items:
        return {"status": "empty", "mode": "none", "reports": []}

    unsent = [it for it in raw_items if it.get("researchId") not in sent_ids]
    today_unsent = [it for it in unsent if it.get("writeDate") == today_str]

    if len(today_unsent) >= min_today_count:
        reports = fetch_report_details(today_unsent, limit=limit)
        return {"status": "ready", "mode": "today", "reports": reports}

    if not allow_fallback:
        return {
            "status": "wait",
            "mode": "waiting_for_more",
            "today_count": len(today_unsent),
            "reports": [],
        }

    # allow_fallback=True: 오늘 리포트(있다면 우선 포함) + 최근 미발송 리포트로 채움
    older_unsent = [it for it in unsent if it.get("writeDate") != today_str]
    combined = today_unsent + older_unsent
    if not combined:
        return {"status": "empty", "mode": "all_sent", "reports": []}

    mode = "mixed" if today_unsent else "next_best"
    reports = fetch_report_details(combined, limit=limit)
    return {"status": "ready", "mode": mode, "reports": reports}


def download_pdf(pdf_url: str, research_id: int) -> Optional[str]:
    """리포트 PDF를 임시 폴더에 다운로드하고 경로를 반환한다."""
    os.makedirs(TMP_PDF_DIR, exist_ok=True)
    pdf_path = os.path.join(TMP_PDF_DIR, f"{research_id}.pdf")
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1024:
        return pdf_path

    try:
        resp = requests.get(pdf_url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        with open(pdf_path, "wb") as f:
            f.write(resp.content)
        return pdf_path
    except Exception as e:
        print(f"[수집] PDF 다운로드 실패 (id={research_id}): {e}")
        return None
