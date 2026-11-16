import base64
import json
import re
import time
import requests
from typing import Dict, List, Optional
from .config import get_env

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


def _call_gemini(parts: List[Dict], json_mode: bool = True, max_retries: int = 3) -> Optional[str]:
    api_key = get_env("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.3,
        },
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{GEMINI_ENDPOINT}?key={api_key}",
                json=payload,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                cands = data.get("candidates", [])
                if cands:
                    return cands[0]["content"]["parts"][0].get("text", "")
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 3 * (attempt + 1)
                print(f"[Gemini] HTTP {resp.status_code}, {wait}초 후 재시도...")
                time.sleep(wait)
                continue
            print(f"[Gemini] 오류 HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        except Exception as e:
            print(f"[Gemini] 예외 발생: {e}")
            time.sleep(2)
    return None


def _parse_json_safe(text: Optional[str]) -> Optional[Dict]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def select_top_reports(reports: List[Dict], top_n: int = 3) -> List[Dict]:
    """수집된 데일리 리포트 중 투자 학습 및 시장 파악 가치가 높은 Top N을 선별한다."""
    if len(reports) <= top_n:
        return reports

    summary_lines = []
    for r in reports:
        summary_lines.append(
            f"- ID: {r['research_id']} | 증권사: {r['broker']} | 조회수: {r['read_count']} | "
            f"제목: {r['title']}\n  요약: {r['snippet'][:220]}"
        )

    prompt = (
        "당신은 개인 투자자의 시장 분석 역량을 키워주는 수석 리서치 에디터입니다.\n"
        f"아래 오늘자 네이버 증권 데일리 리서치 목록 중에서, 단순 지수 등락 나열이나 단발성 상품 홍보가 아닌 "
        f"'시장 흐름 파악·투자 아이디어·차트 학습 가치'가 가장 높은 리포트 {top_n}개를 엄선하세요.\n"
        "가능하면 서로 다른 증권사나 주제(전략, 시황, 매크로/섹터 등)가 균형 있게 섞이도록 고르세요.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        '{"selected_ids": [12345, 12346, 12347], "reasons": {"12345": "선정 이유"}}\n\n'
        "[리포트 목록]\n" + "\n".join(summary_lines)
    )

    raw = _call_gemini([{"text": prompt}], json_mode=True)
    parsed = _parse_json_safe(raw)

    report_map = {r["research_id"]: r for r in reports}
    selected = []
    if parsed and isinstance(parsed.get("selected_ids"), list):
        reasons = parsed.get("reasons", {})
        for rid in parsed["selected_ids"]:
            try:
                rid_int = int(rid)
            except Exception:
                continue
            if rid_int in report_map and report_map[rid_int] not in selected:
                item = dict(report_map[rid_int])
                item["pick_reason"] = reasons.get(str(rid_int), "")
                selected.append(item)

    if len(selected) < top_n:
        # 부족분은 조회수 순으로 보충
        by_views = sorted(reports, key=lambda x: x.get("read_count", 0), reverse=True)
        for r in by_views:
            if len(selected) >= top_n:
                break
            if all(s["research_id"] != r["research_id"] for s in selected):
                selected.append(dict(r))

    return selected[:top_n]


def analyze_report_multimodal(
    report: Dict, full_text: str, total_pages: int, candidates: List[Dict]
) -> Dict:
    """
    리포트 PDF 본문 텍스트와 후보 차트 페이지 이미지들을 Gemini 멀티모달로 분석하여
    구조화된 학습형 매거진 콘텐츠를 생성한다.
    """
    cand_pages = [c["page"] for c in candidates]
    prompt = (
        "당신은 한국 주식·글로벌 매크로 애널리스트이자 투자 멘토입니다.\n"
        "첨부된 증권사 데일리 리포트의 텍스트와 페이지 이미지(차트/도표 후보)를 함께 읽고, "
        "바쁜 직장인 투자자가 모바일에서 1~2분 안에 핵심을 파악하고 '차트를 읽는 눈(투자 역량)'을 기를 수 있도록 분석해 주세요.\n\n"
        f"- 리포트 제목: {report['title']}\n"
        f"- 증권사: {report['broker']}\n"
        f"- 작성일: {report['write_date']}\n"
        f"- 전체 페이지 수: {total_pages}p\n"
        f"- 첨부된 이미지 페이지 번호 목록: {cand_pages}\n\n"
        "반드시 아래 JSON 스키마로만 정확히 응답하세요:\n"
        "{\n"
        '  "category_tag": "전략·시황 | 매크로·금리 | 산업·섹터 | 수급·퀀트 중 하나",\n'
        '  "one_line_hook": "텔레그램 알림용 2줄 인과관계 핵심 요약 (반드시 줄바꿈 \\n 으로 구분된 2문장. 단순 결론/조언 금지, 반드시 \'왜 그런지\' 근거·원인·수치를 포함할 것. 1줄째: 핵심 현상과 그렇게 된 구체적 원인/수치, 2줄째: 그 현상이 왜 특정 섹터/전략으로 이어지는지 논리적 근거와 시사점. 각 줄 55~70자 내외)",\n'
        '  "executive_summary": "🎯 30초 핵심 결론 (2~3문장, 구체적 수치와 논리 포함)",\n'
        '  "best_chart_pages": [첨부된 이미지 페이지 번호 중 가장 핵심 차트가 담긴 1~2개 정수],\n'
        '  "chart_title": "선택한 핵심 차트/도표의 제목 (예: 미국 빅테크 Capex vs 잉여현금흐름 추이)",\n'
        '  "chart_reading_tip": "🔍 핵심 차트 독해 팁: 위 이미지의 차트에서 어떤 지표/선/변곡점을 봐야 하는지, 애널리스트가 왜 이 그래프를 근거로 삼았는지 초보자도 이해하기 쉽게 3~4문장으로 설명",\n'
        '  "key_takeaways": [\n'
        '    "투자 시사점/액션 포인트 1 (구체적 섹터·자산군·대응 전략)",\n'
        '    "투자 시사점/액션 포인트 2"\n'
        "  ],\n"
        '  "glossary": [\n'
        '    {"term": "리포트에 나온 핵심 금융/경제 용어", "desc": "초보자 눈높이의 1~2줄 쉬운 해설"}\n'
        "  ]\n"
        "}\n\n"
        "[리포트 본문 텍스트]\n" + full_text[:7000]
    )

    parts: List[Dict] = [{"text": prompt}]
    for c in candidates:
        try:
            with open(c["image_path"], "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode("utf-8")
            parts.append({"text": f"[참고 이미지: Page {c['page']}]"})
            parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
        except Exception as e:
            print(f"[분석] 이미지 인코딩 실패 (p{c['page']}): {e}")

    raw = _call_gemini(parts, json_mode=True)
    parsed = _parse_json_safe(raw)

    if not parsed:
        # 안전망 폴백
        return {
            "category_tag": "데일리 리서치",
            "one_line_hook": report["title"][:35],
            "executive_summary": report.get("snippet", "")[:260] or report["title"],
            "best_chart_pages": cand_pages[:1],
            "chart_title": f"{report['broker']} 리포트 핵심 페이지",
            "chart_reading_tip": "리포트 본문과 차트를 통해 오늘 시장의 핵심 변수와 애널리스트의 논리 근거를 확인해 보세요.",
            "key_takeaways": [f"원본 PDF({total_pages}p)에서 세부 수치와 종목별 코멘트를 참고하세요."],
            "glossary": [],
        }

    # best_chart_pages 검증
    valid_pages = [
        int(p) for p in parsed.get("best_chart_pages", [])
        if isinstance(p, (int, float, str)) and str(p).isdigit() and int(p) in cand_pages
    ]
    if not valid_pages and cand_pages:
        valid_pages = cand_pages[:1]
    parsed["best_chart_pages"] = valid_pages[:2]
    return parsed
