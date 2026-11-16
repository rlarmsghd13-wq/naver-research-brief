import os
from typing import Dict, List, Optional
from PIL import Image, ImageChops, ImageDraw, ImageFont
from .config import DOCS_DIR

CARDS_DIR = os.path.join(DOCS_DIR, "assets", "cards")


def _find_font(bold: bool = False) -> Optional[str]:
    """Windows 및 Linux(GitHub Actions) 환경에서 사용 가능한 한글 폰트를 찾는다."""
    if bold:
        candidates = [
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _find_font(bold=bold)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """픽셀 너비 기준으로 한글/영문 혼합 텍스트를 자연스럽게 줄바꿈한다."""
    lines: List[str] = []
    for paragraph in (text or "").splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for ch in paragraph:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current.strip())
                current = ch
        if current:
            lines.append(current.strip())
    return lines


def _trim_whitespace(im: Image.Image, margin: int = 16) -> Image.Image:
    """PDF 렌더링 이미지의 불필요한 바깥 흰 여백을 자동으로 잘라내어 차트를 더 크게 표시한다."""
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im.convert("RGB"), bg)
    bbox = diff.getbbox()
    if not bbox:
        return im
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(im.width, bbox[2] + margin)
    bottom = min(im.height, bbox[3] + margin)
    return im.crop((left, top, right, bottom))


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def generate_card_image(item: Dict, index: int, date_str: str) -> str:
    """
    단일 리포트(Pick)에 대한 차트 중심 대형 카드뉴스 PNG를 생성하고 상대 URL을 반환한다.
    상단에는 제목과 1줄 핵심만 슬림하게 배치하고, 나머지 영역 전체를 고화질 차트로 채운다.
    """
    out_dir = os.path.join(CARDS_DIR, date_str)
    os.makedirs(out_dir, exist_ok=True)

    W = 1080
    pad = 32
    content_w = W - pad * 2

    f_badge = _load_font(24, bold=True)
    f_meta = _load_font(24, bold=False)
    f_title = _load_font(40, bold=True)
    f_sub = _load_font(26, bold=False)
    f_small = _load_font(22, bold=False)

    # 임시 캔버스로 텍스트 높이 측정
    tmp = Image.new("RGB", (W, 400), "#0F172A")
    tdraw = ImageDraw.Draw(tmp)
    title_lines = _wrap_text(tdraw, item.get("title", ""), f_title, content_w)[:2]

    hook_raw = (item.get("one_line_hook") or "").strip()
    first_hook = next((ln.strip() for ln in hook_raw.splitlines() if ln.strip()), "")
    sub_lines = _wrap_text(tdraw, first_hook, f_sub, content_w)[:2] if first_hook else []

    header_h = 34 + 44 + 18 + (len(title_lines) * 52) + (len(sub_lines) * 36 + 10 if sub_lines else 0) + 18

    # 차트 이미지 준비 및 리사이즈 (가로 100% 꽉 채움)
    c_img = None
    charts = item.get("charts", [])
    if charts:
        chart_rel = charts[0].get("url", "")
        chart_abs = os.path.join(DOCS_DIR, chart_rel) if chart_rel else ""
        if chart_abs and os.path.exists(chart_abs):
            try:
                raw_im = Image.open(chart_abs).convert("RGB")
                trimmed = _trim_whitespace(raw_im, margin=18)
                target_w = content_w - 24
                ratio = target_w / trimmed.width
                target_h = int(trimmed.height * ratio)
                # 너무 길어지지 않도록 최대 높이 제한 (최대 1500px)
                if target_h > 1500:
                    target_h = 1500
                    target_w = int(trimmed.width * (target_h / trimmed.height))
                c_img = trimmed.resize((target_w, target_h), Image.Resampling.LANCZOS)
            except Exception as e:
                print(f"[카드뉴스] 차트 로드 실패: {e}")

    chart_box_h = (52 + c_img.height + 16) if c_img else 300
    footer_h = 54
    H = header_h + chart_box_h + footer_h

    img = Image.new("RGB", (W, H), "#0F172A")
    draw = ImageDraw.Draw(img)

    # 1) 상단 배지 & 메타
    _draw_rounded_rect(draw, (pad, 34, pad + 210, 78), radius=10, fill="#3182F6")
    draw.text((pad + 18, 42), f"DAILY PICK #{index}", font=f_badge, fill="#FFFFFF")

    tag_text = item.get("category_tag", "리서치")
    _draw_rounded_rect(draw, (pad + 224, 34, pad + 388, 78), radius=10, fill="#1E293B", outline="#334155")
    draw.text((pad + 244, 42), tag_text, font=f_badge, fill="#93C5FD")

    meta_text = f"{item.get('broker', '')} · {date_str}"
    mb = draw.textbbox((0, 0), meta_text, font=f_meta)
    draw.text((W - pad - (mb[2] - mb[0]), 42), meta_text, font=f_meta, fill="#94A3B8")

    # 2) 제목 & 핵심 1줄
    y = 96
    for tl in title_lines:
        draw.text((pad, y), tl, font=f_title, fill="#F8FAFC")
        y += 52
    if sub_lines:
        y += 6
        for sl in sub_lines:
            draw.text((pad, y), sl, font=f_sub, fill="#93C5FD")
            y += 36
    y += 14

    # 3) 대형 차트 카드 영역
    _draw_rounded_rect(draw, (pad, y, W - pad, y + chart_box_h), radius=18, fill="#FFFFFF")
    chart_title = item.get("chart_title") or "핵심 차트"
    draw.text((pad + 20, y + 14), f"[핵심 차트] {chart_title[:48]}", font=f_small, fill="#1E293B")
    if c_img:
        cx = pad + (content_w - c_img.width) // 2
        cy = y + 48
        img.paste(c_img, (cx, cy))

    # 4) 푸터
    fy = y + chart_box_h + 14
    draw.text((pad, fy), "MORNING RESEARCH MAGAZINE", font=f_small, fill="#64748B")
    right_footer = "세부 독해 팁·용어 해설은 아래 매거진 버튼에서"
    rb = draw.textbbox((0, 0), right_footer, font=f_small)
    draw.text((W - pad - (rb[2] - rb[0]), fy), right_footer, font=f_small, fill="#64748B")

    filename = f"{item['research_id']}_card.png"
    out_path = os.path.join(out_dir, filename)
    img.save(out_path, format="PNG", optimize=True)
    return f"assets/cards/{date_str}/{filename}"
