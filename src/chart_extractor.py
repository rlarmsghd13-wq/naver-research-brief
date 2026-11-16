import os
import shutil
from typing import Dict, List, Tuple
import pymupdf as fitz
from .config import CHARTS_DIR, TMP_PDF_DIR


def extract_pdf_content_and_candidates(
    pdf_path: str, research_id: int, max_pages_to_scan: int = 8, max_candidates: int = 4
) -> Tuple[str, int, List[Dict]]:
    """
    PDF에서 전체 텍스트, 페이지 수, 그리고 차트/도표가 포함된 후보 페이지 이미지들을 추출한다.
    반환: (full_text, total_pages, [{"page": int, "image_path": str, "score": int}, ...])
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    texts = []
    page_scores = []

    scan_limit = min(total_pages, max_pages_to_scan)
    for idx in range(scan_limit):
        page = doc[idx]
        text = page.get_text("text").strip()
        if text:
            texts.append(f"[Page {idx + 1}]\n{text}")

        # 면책조항/Compliance 페이지 감점
        lower_t = text.lower()
        if any(kw in lower_t for kw in ["compliance notice", "투자 유의사항", "면책", "금융투자상품"]):
            if idx == total_pages - 1 or len(text) < 600:
                continue

        # 벡터 드로잉 수 + 래스터 이미지 수로 차트 밀집도 추정
        drawings_count = len(page.get_drawings())
        images_count = len(page.get_images(full=True))
        score = drawings_count + (images_count * 25)

        # 1페이지는 제목/표지 위주인 경우가 많으나 1~2페이지짜리 데일리 시황은 1페이지에 차트가 있음
        if total_pages > 2 and idx == 0 and drawings_count < 15 and images_count == 0:
            score = max(0, score - 20)

        if score > 10 or total_pages <= 3:
            page_scores.append((score, idx))

    # 점수 높은 순으로 상위 후보 추출 (단, 최소 1페이지는 포함)
    if not page_scores and total_pages > 0:
        page_scores = [(1, 0)]

    page_scores.sort(key=lambda x: x[0], reverse=True)
    selected_indices = sorted([idx for _, idx in page_scores[:max_candidates]])

    cand_dir = os.path.join(TMP_PDF_DIR, f"pages_{research_id}")
    os.makedirs(cand_dir, exist_ok=True)

    candidates = []
    for idx in selected_indices:
        page = doc[idx]
        # 2.0x 줌 (~144~180 DPI 수준)으로 선명하게 렌더링
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_path = os.path.join(cand_dir, f"page_{idx + 1}.png")
        pix.save(img_path)
        candidates.append({
            "page": idx + 1,
            "image_path": img_path,
        })

    doc.close()
    full_text = "\n\n".join(texts)[:9000]
    return full_text, total_pages, candidates


def publish_chart_images(
    date_str: str, research_id: int, candidates: List[Dict], chosen_pages: List[int]
) -> List[Dict]:
    """
    Gemini가 선택한 핵심 차트 페이지 이미지를 docs/assets/charts/{date_str}/ 로 복사하고
    웹 매거진에서 사용할 상대 경로와 메타데이터를 반환한다.
    """
    out_dir = os.path.join(CHARTS_DIR, date_str)
    os.makedirs(out_dir, exist_ok=True)

    cand_map = {c["page"]: c["image_path"] for c in candidates}
    published = []

    for p in chosen_pages:
        if p in cand_map and os.path.exists(cand_map[p]):
            filename = f"{research_id}_p{p}.png"
            dst = os.path.join(out_dir, filename)
            shutil.copyfile(cand_map[p], dst)
            published.append({
                "page": p,
                "url": f"assets/charts/{date_str}/{filename}",
                "local_path": dst,
            })

    # 선택된 페이지가 매칭되지 않으면 첫 번째 후보라도 안전하게 포함
    if not published and candidates:
        first = candidates[0]
        filename = f"{research_id}_p{first['page']}.png"
        dst = os.path.join(out_dir, filename)
        shutil.copyfile(first["image_path"], dst)
        published.append({
            "page": first["page"],
            "url": f"assets/charts/{date_str}/{filename}",
            "local_path": dst,
        })

    return published
