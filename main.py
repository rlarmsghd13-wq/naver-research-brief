import argparse
import sys
from src.config import get_kst_now
from src.fetcher import fetch_smart_candidates, download_pdf
from src.chart_extractor import extract_pdf_content_and_candidates, publish_chart_images
from src.analyzer import select_top_reports, analyze_report_multimodal
from src.web_builder import (
    is_date_already_published,
    load_sent_ids,
    save_magazine_data,
)
from src.card_generator import generate_card_image
from src.notifier import send_hybrid_notification


def run_pipeline(
    target_date: str = "",
    top_n: int = 3,
    min_today: int = 5,
    allow_fallback: bool = True,
    force: bool = False,
    dry_run: bool = False,
):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    today_str = target_date or get_kst_now().strftime("%Y-%m-%d")
    print(f"=== 네이버 증권 데일리 리서치 하이브리드 브리프 시작 (기준일: {today_str}) ===")

    if not force and is_date_already_published(today_str):
        print(f"[스킵] {today_str} 브리프는 이미 생성 및 발송 완료되었습니다. (--force 로 재실행 가능)")
        return

    sent_ids = load_sent_ids()
    print(f"[이력] 기존 발송 완료 리포트 {len(sent_ids)}건 제외 대상 로드")

    fetch_res = fetch_smart_candidates(
        today_str=today_str,
        sent_ids=sent_ids,
        min_today_count=min_today,
        allow_fallback=allow_fallback,
        limit=18,
    )

    status = fetch_res["status"]
    mode = fetch_res["mode"]
    if status == "wait":
        print(
            f"[대기] {today_str} 신규 리포트가 아직 {fetch_res.get('today_count', 0)}건으로 "
            f"기준({min_today}건) 미만입니다. 다음 스케줄에서 재확인합니다."
        )
        return
    if status == "empty" or not fetch_res["reports"]:
        print("[중단] 발송 가능한 신규 리포트 후보가 없습니다.")
        return

    reports = fetch_res["reports"]
    print(f"[수집] 후보 리포트 {len(reports)}건 확보 (mode={mode})")

    picks = select_top_reports(reports, top_n=top_n)
    print(f"[선별] Daily Pick {len(picks)}건 선정 완료:")
    for i, p in enumerate(picks, 1):
        print(f"  {i}. [{p['broker']}] {p['title']} ({p['write_date']}, 조회 {p['read_count']})")

    analyzed_items = []
    for idx, rep in enumerate(picks, 1):
        rid = rep["research_id"]
        print(f"\n[분석 {idx}/{len(picks)}] {rep['broker']} - {rep['title']} (id={rid})")
        pdf_path = download_pdf(rep["pdf_url"], rid)
        if not pdf_path:
            continue

        full_text, total_pages, candidates = extract_pdf_content_and_candidates(pdf_path, rid)
        print(f"  - PDF {total_pages}p 추출, 차트 후보 {len(candidates)}장 생성")

        analysis = analyze_report_multimodal(rep, full_text, total_pages, candidates)
        charts = publish_chart_images(
            today_str, rid, candidates, analysis.get("best_chart_pages", [])
        )
        print(f"  - 최종 선정 차트 {len(charts)}장 발행: {[c['page'] for c in charts]}")

        item_data = {
            "research_id": rid,
            "title": rep["title"],
            "broker": rep["broker"],
            "write_date": rep["write_date"],
            "read_count": rep["read_count"],
            "total_pages": total_pages,
            "pdf_url": rep["pdf_url"],
            "naver_url": rep["naver_url"],
            "pick_reason": rep.get("pick_reason", ""),
            "category_tag": analysis.get("category_tag", "데일리 리서치"),
            "one_line_hook": analysis.get("one_line_hook", ""),
            "executive_summary": analysis.get("executive_summary", ""),
            "chart_title": analysis.get("chart_title", ""),
            "chart_reading_tip": analysis.get("chart_reading_tip", ""),
            "key_takeaways": analysis.get("key_takeaways", []),
            "glossary": analysis.get("glossary", []),
            "charts": [{"page": c["page"], "url": c["url"]} for c in charts],
        }
        try:
            card_url = generate_card_image(item_data, idx, today_str)
            item_data["card_url"] = card_url
            print(f"  - 카드뉴스 생성 완료: {card_url}")
        except Exception as e:
            print(f"  - 카드뉴스 생성 실패 (무시): {e}")

        analyzed_items.append(item_data)

    if not analyzed_items:
        print("[중단] 분석에 성공한 리포트가 없습니다.")
        return

    payload = save_magazine_data(today_str, analyzed_items, mode=mode)

    if dry_run:
        print("\n[Dry-Run] 텔레그램 발송은 건너뛰었습니다.")
    else:
        send_hybrid_notification(payload)

    print("\n=== 파이프라인 완료 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 리서치 하이브리드 매거진 빌더")
    parser.add_argument("--date", type=str, default="", help="기준 날짜 (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=3, help="선별할 리포트 수 (기본 3)")
    parser.add_argument("--min-today", type=int, default=5, help="당일 리포트 최소 기준 건수 (기본 5)")
    parser.add_argument("--no-fallback", action="store_true", help="당일 리포트 부족 시 최근 미발송 대체 없이 대기")
    parser.add_argument("--force", action="store_true", help="오늘 이미 발송되었어도 강제 재실행")
    parser.add_argument("--dry-run", action="store_true", help="텔레그램 발송 없이 웹 데이터만 빌드")
    args = parser.parse_args()

    run_pipeline(
        target_date=args.date,
        top_n=args.top,
        min_today=args.min_today,
        allow_fallback=not args.no_fallback,
        force=args.force,
        dry_run=args.dry_run,
    )
