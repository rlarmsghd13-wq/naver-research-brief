import os
import textwrap
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont
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


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def generate_card_image(item: Dict, index: int, date_str: str) -> str:
    """
    단일 리포트(Pick)에 대한 1080x1350 모바일 카드뉴스 PNG를 생성하고 상대 URL을 반환한다.
    """
    out_dir = os.path.join(CARDS_DIR, date_str)
    os.makedirs(out_dir, exist_ok=True)

    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), "#0F172A")  # 다크 네이비 프리미엄 배경
    draw = ImageDraw.Draw(img)

    # 폰트
    f_badge = _load_font(26, bold=True)
    f_meta = _load_font(26, bold=False)
    f_title = _load_font(46, bold=True)
    f_sec_title = _load_font(28, bold=True)
    f_body = _load_font(30, bold=False)
    f_small = _load_font(24, bold=False)

    pad = 56
    content_w = W - pad * 2

    # 1) 상단 배지 & 증권사 메타
    badge_text = f"DAILY PICK #{index}"
    _draw_rounded_rect(draw, (pad, 48, pad + 230, 96), radius=12, fill="#3182F6")
    draw.text((pad + 22, 57), badge_text, font=f_badge, fill="#FFFFFF")

    tag_text = item.get("category_tag", "리서치")
    _draw_rounded_rect(draw, (pad + 246, 48, pad + 420, 96), radius=12, fill="#1E293B", outline="#334155")
    draw.text((pad + 268, 57), tag_text, font=f_badge, fill="#93C5FD")

    meta_text = f"{item.get('broker', '')} · {date_str}"
    mb = draw.textbbox((0, 0), meta_text, font=f_meta)
    draw.text((W - pad - (mb[2] - mb[0]), 57), meta_text, font=f_meta, fill="#94A3B8")

    # 2) 리포트 제목
    y = 128
    title_lines = _wrap_text(draw, item.get("title", ""), f_title, content_w)[:2]
    for tl in title_lines:
        draw.text((pad, y), tl, font=f_title, fill="#F8FAFC")
        y += 60
    y += 18

    # 3) 박스 1: 왜 이런 흐름인가? (인과관계 2줄 요약)
    hook_raw = (item.get("one_line_hook") or "").strip()
    hook_lines_raw = [ln.strip() for ln in hook_raw.splitlines() if ln.strip()]
    if not hook_lines_raw:
        hook_lines_raw = [item.get("executive_summary", "").replace("🎯", "").strip()]

    wrapped_hook: List[str] = []
    for hl in hook_lines_raw[:2]:
        wrapped_hook.extend(_wrap_text(draw, f"• {hl}", f_body, content_w - 56)[:3])

    box1_h = 74 + len(wrapped_hook) * 44 + 24
    _draw_rounded_rect(draw, (pad, y, W - pad, y + box1_h), radius=20, fill="#1E293B", outline="#334155")
    draw.text((pad + 28, y + 22), "핵심 원인 & 인과 요약", font=f_sec_title, fill="#60A5FA")
    cy = y + 68
    for wl in wrapped_hook:
        draw.text((pad + 28, cy), wl, font=f_body, fill="#E2E8F0")
        cy += 44
    y += box1_h + 22

    # 4) 박스 2: 투자 시사점 (액션 포인트)
    takeaways = item.get("key_takeaways", [])
    take_text = takeaways[0] if takeaways else item.get("chart_reading_tip", "").replace("🔍", "").strip()
    wrapped_take = _wrap_text(draw, take_text, f_body, content_w - 56)[:3]
    box2_h = 74 + len(wrapped_take) * 44 + 24
    _draw_rounded_rect(draw, (pad, y, W - pad, y + box2_h), radius=20, fill="#172554", outline="#2563EB")
    draw.text((pad + 28, y + 22), "투자 시사점 & 대응", font=f_sec_title, fill="#93C5FD")
    cy = y + 68
    for wl in wrapped_take:
        draw.text((pad + 28, cy), wl, font=f_body, fill="#DBEAFE")
        cy += 44
    y += box2_h + 24

    # 5) 하단 차트 썸네일 영역 (남은 공간 활용)
    footer_h = 66
    avail_h = H - y - footer_h - 16
    charts = item.get("charts", [])
    if charts and avail_h > 220:
        chart_rel = charts[0].get("url", "")
        chart_abs = os.path.join(DOCS_DIR, chart_rel) if chart_rel else ""
        if chart_abs and os.path.exists(chart_abs):
            _draw_rounded_rect(draw, (pad, y, W - pad, y + avail_h), radius=20, fill="#FFFFFF")
            chart_title = item.get("chart_title") or "핵심 차트 미리보기"
            draw.text((pad + 24, y + 16), f"Chart: {chart_title[:42]}", font=f_small, fill="#334155")
            try:
                c_img = Image.open(chart_abs).convert("RGB")
                max_cw = content_w - 32
                max_ch = avail_h - 62
                c_img.thumbnail((max_cw, max_ch), Image.Resampling.LANCZOS)
                cx = pad + (content_w - c_img.width) // 2
                cy = y + 52 + (max_ch - c_img.height) // 2
                img.paste(c_img, (cx, cy))
            except Exception as e:
                print(f"[카드뉴스] 차트 삽입 실패: {e}")

    # 6) 푸터
    draw.text((pad, H - 52), "MORNING RESEARCH MAGAZINE", font=f_small, fill="#64748B")
    right_footer = "자세한 차트 확대·용어 해설은 웹 매거진에서"
    rb = draw.textbbox((0, 0), right_footer, font=f_small)
    draw.text((W - pad - (rb[2] - rb[0]), H - 52), right_footer, font=f_small, fill="#64748B")

    filename = f"{item['research_id']}_card.png"
    out_path = os.path.join(out_dir, filename)
    img.save(out_path, format="PNG", optimize=True)
    return f"assets/cards/{date_str}/{filename}"
