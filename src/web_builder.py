import json
import os
from typing import Dict, List, Set
from .config import ARCHIVE_DIR, DATA_DIR, get_kst_now

SENT_IDS_PATH = os.path.join(DATA_DIR, "sent_ids.json")


def load_sent_ids() -> Set[int]:
    """기존 아카이브 및 sent_ids.json에서 이미 발송 완료된 research_id 집합을 불러온다."""
    ids: Set[int] = set()
    if os.path.exists(SENT_IDS_PATH):
        try:
            with open(SENT_IDS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for x in data.get("ids", []):
                    ids.add(int(x))
        except Exception:
            pass

    if os.path.exists(ARCHIVE_DIR):
        for fn in os.listdir(ARCHIVE_DIR):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(ARCHIVE_DIR, fn), "r", encoding="utf-8") as f:
                        d = json.load(f)
                        for p in d.get("picks", []):
                            if p.get("research_id"):
                                ids.add(int(p["research_id"]))
                except Exception:
                    pass
    return ids


def append_sent_ids(new_ids: List[int]):
    """새로 발송한 research_id들을 sent_ids.json에 누적 저장한다 (최대 300개)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    existing: List[int] = []
    if os.path.exists(SENT_IDS_PATH):
        try:
            with open(SENT_IDS_PATH, "r", encoding="utf-8") as f:
                existing = [int(x) for x in json.load(f).get("ids", [])]
        except Exception:
            existing = []

    for nid in new_ids:
        if nid not in existing:
            existing.append(nid)

    trimmed = existing[-300:]
    with open(SENT_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump({"ids": trimmed}, f, ensure_ascii=False, indent=2)


def is_date_already_published(date_str: str) -> bool:
    return os.path.exists(os.path.join(ARCHIVE_DIR, f"{date_str}.json"))


def save_magazine_data(date_str: str, items: List[Dict], mode: str = "today") -> Dict:
    """
    분석된 Pick 3 리포트 데이터를 정적 웹 매거진용 JSON으로 저장한다.
    """
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    payload = {
        "date": date_str,
        "mode": mode,
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

    append_sent_ids([int(it["research_id"]) for it in items if it.get("research_id")])
    print(f"[웹빌드] {date_str} 데이터 저장 완료 (총 {len(items)}건, mode={mode}, 아카이브 {len(dates)}일)")
    return payload
