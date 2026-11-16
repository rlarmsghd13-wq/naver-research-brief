import argparse
import os
import sys
from src.config import get_kst_now
from src.fetcher import fetch_daily_reports, download_pdf
from src.chart_extractor import extract_pdf_content_and_candidates, publish_chart_images
from src.analyzer import select_top_reports, analyze_report_multimodal
from src.web_builder import save_magazine_data
from src.card_generator import generate_card_image
from src.notifier import send_hybrid_notification


def run_pipeline(target_date: str = "", top_n: int = 3, dry_run: bool = False):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=== 네이버 증권 데일리 리서치 하이브리드 브리프 시작 ===")
    reports = fetch_daily_reports(target_date=target_date or None, limit=15)
    if not reports:
        print("[중단] 수집된 데일리 리서치가 없습니다.")
        return

    actual_date = reports[0]["write_date"]
    print(f"[수집] 기준일 {actual_date} 리포트 {len(reports)}건 확보")

    picks = select_top_reports(reports, top_n=top_n)
    print(f"[선별] Daily Pick {len(picks)}건 선정 완료:")
    for i, p in enumerate(picks, 1):
        print(f"  {i}. [{p['broker']}] {p['title']} (조회 {p['read_count']})")

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
            actual_date, rid, candidates, analysis.get("best_chart_pages", [])
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
            card_url = generate_card_image(item_data, idx, actual_date)
            item_data["card_url"] = card_url
            print(f"  - 카드뉴스 생성 완료: {card_url}")
        except Exception as e:
            print(f"  - 카드뉴스 생성 실패 (무시): {e}")

        analyzed_items.append(item_data)

    if not analyzed_items:
        print("[중단] 분석에 성공한 리포트가 없습니다.")
        return

    payload = save_magazine_data(actual_date, analyzed_items)

    if dry_run:
        print("\n[Dry-Run] 텔레그램 발송은 건너뛰었습니다.")
    else:
        send_hybrid_notification(payload)

    print("\n=== 파이프라인 완료 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 리서치 하이브리드 매거진 빌더")
    parser.add_argument("--date", type=str, default="", help="조회할 날짜 (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=3, help="선별할 리포트 수 (기본 3)")
    parser.add_argument("--dry-run", action="store_true", help="텔레그램 발송 없이 웹 데이터만 빌드")
    args = parser.parse_args()

    run_pipeline(target_date=args.date, top_n=args.top, dry_run=args.dry_run)
