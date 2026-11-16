import os
import re
import html
import requests
from typing import List, Dict, Optional
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


def fetch_daily_reports(target_date: Optional[str] = None, limit: int = 15) -> List[Dict]:
    """네이버 증권 데일리 리서치 목록 및 상세 정보(PDF URL 포함)를 수집한다."""
    resp = requests.get(LIST_API, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    items = resp.json()
    if not items:
        return []

    # target_date가 주어지지 않으면 목록 중 가장 최신 writeDate를 기준으로 삼음
    latest_date = target_date or items[0].get("writeDate", "")
    filtered = [it for it in items if it.get("writeDate") == latest_date]
    if not filtered:
        # 해당 날짜가 없으면 가장 최신 날짜 전체 사용
        latest_date = items[0].get("writeDate", "")
        filtered = [it for it in items if it.get("writeDate") == latest_date]

    reports = []
    for it in filtered[:limit]:
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
            "write_date": detail.get("writeDate") or it.get("writeDate", latest_date),
            "read_count": int(detail.get("readCount") or it.get("readCount") or 0),
            "pdf_url": attach_url,
            "naver_url": it.get("endUrl", f"https://m.stock.naver.com/research/daily/{rid}"),
            "snippet": _clean_html(detail.get("content", "")),
        })

    return reports


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
