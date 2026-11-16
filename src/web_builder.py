import json
import os
from typing import Dict, List
from .config import ARCHIVE_DIR, DATA_DIR, get_kst_now


def save_magazine_data(date_str: str, items: List[Dict]) -> Dict:
    """
    분석된 Pick 3 리포트 데이터를 정적 웹 매거진용 JSON으로 저장한다.
    - docs/data/archive/{date_str}.json
    - docs/data/latest.json
    - docs/data/dates.json
    """
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    payload = {
        "date": date_str,
        "generated_at": get_kst_now().strftime("%Y-%m-%d %H:%M KST"),
        "count": len(items),
        "picks": items,
    }

    archive_path = os.path.join(ARCHIVE_DIR, f"{date_str}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    latest_path = os.path.join(DATA_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 날짜 인덱스 갱신 (최신순)
    dates = []
    for fn in os.listdir(ARCHIVE_DIR):
        if fn.endswith(".json"):
            dates.append(fn[:-5])
    dates.sort(reverse=True)

    dates_path = os.path.join(DATA_DIR, "dates.json")
    with open(dates_path, "w", encoding="utf-8") as f:
        json.dump({"dates": dates[:60]}, f, ensure_ascii=False, indent=2)

    print(f"[웹빌드] {date_str} 데이터 저장 완료 (총 {len(items)}건, 아카이브 {len(dates)}일)")
    return payload
