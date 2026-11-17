import html
import json
import os
import requests
from typing import Dict, List
from .config import DOCS_DIR, get_env


def _get_chat_ids() -> List[str]:
    raw = get_env("TELEGRAM_CHAT_ID")
    return [cid.strip() for cid in raw.split(",") if cid.strip()]


def send_hybrid_notification(payload: Dict) -> bool:
    """
    방안 C (하이브리드):
    대표 차트 이미지 1장을 포토 메시지로 먼저 전송(또는 요약 텍스트)하고,
    Pick 1~3 핵심 요약 + 모바일 리서치 매거진 원터치 버튼을 발송한다.
    """
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_ids = _get_chat_ids()
    web_url = get_env("WEB_APP_URL")

    if not token or not chat_ids:
        print("[텔레그램] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 없어 전송을 건너뜁니다.")
        return False

    date_str = payload.get("date", "")
    mode = payload.get("mode", "today")
    picks = payload.get("picks", [])
    if not picks:
        return False

    mode_badge = ""
    if mode == "next_best":
        mode_badge = " · <i>최근 미발송 베스트</i>"
    elif mode == "mixed":
        mode_badge = " · <i>오늘 + 최근 베스트</i>"

    lines = [f"☀️ <b>{html.escape(date_str)} 네이버 리서치 모닝 픽</b>{mode_badge}"]
    for idx, p in enumerate(picks, 1):
        broker = html.escape(p.get("broker", ""))
        title = html.escape(p.get("title", ""))
        tag = html.escape(p.get("category_tag", ""))
        raw_hook = (p.get("one_line_hook") or "").strip()

        # 2줄 요약 보장: 줄바꿈이 없으면 executive_summary 첫 문장을 보충해 2줄로 구성
        hook_lines = [ln.strip() for ln in raw_hook.splitlines() if ln.strip()]
        if len(hook_lines) < 2:
            exec_sum = (p.get("executive_summary") or "").replace("🎯", "").strip()
            sentences = [s.strip() for s in exec_sum.split(". ") if s.strip()]
            if sentences:
                extra = sentences[0] if not hook_lines else (sentences[1] if len(sentences) > 1 else sentences[0])
                if extra and extra not in raw_hook:
                    hook_lines.append(extra[:65] + ("..." if len(extra) > 65 else ""))

        formatted_hook = "\n".join(f"   • {html.escape(ln)}" for ln in hook_lines[:2])
        lines.append(
            f"<b>{idx}. [{broker}] {title}</b> <i>({tag})</i>\n{formatted_hook}"
        )

    lines.append("📊 <i>고화질 차트 확대 · 독해 팁 · 용어 해설은 아래 매거진에서 확인하세요!</i>")
    message_text = "\n\n".join(lines)

    # HTTPS URL이 있을 때만 인라인 키보드 버튼 구성
    reply_markup = None
    if web_url.startswith("https://"):
        buttons = [[{"text": "📱 모바일 리서치 매거진 열기 (차트·해설)", "url": web_url}]]
        if picks[0].get("pdf_url"):
            buttons.append([{"text": "📑 1위 리포트 원본 PDF 바로가기", "url": picks[0]["pdf_url"]}])
        reply_markup = json.dumps({"inline_keyboard": buttons}, ensure_ascii=False)
    elif web_url:
        message_text += f"\n\n🔗 매거진 주소: {html.escape(web_url)}"

    # 각 Pick별 카드뉴스 이미지 경로 수집
    card_items = []
    for idx, p in enumerate(picks, 1):
        c_rel = p.get("card_url", "")
        c_abs = os.path.join(DOCS_DIR, c_rel) if c_rel else ""
        if c_abs and os.path.exists(c_abs):
            card_items.append((idx, p, c_abs))

    # 카드뉴스가 없을 때 폴백: 대표 차트 이미지 1장
    lead_chart_path = ""
    lead_charts = picks[0].get("charts", [])
    if lead_charts and lead_charts[0].get("url"):
        lead_chart_path = os.path.join(DOCS_DIR, lead_charts[0]["url"])

    all_ok = True
    for cid in chat_ids:
        try:
            # 1) Pick별 카드뉴스 앨범(sendMediaGroup) 전송
            if len(card_items) >= 2:
                media = []
                files = {}
                opened = []
                for idx, p, c_abs in card_items:
                    attach_name = f"card_{idx}"
                    f_obj = open(c_abs, "rb")
                    opened.append(f_obj)
                    files[attach_name] = (os.path.basename(c_abs), f_obj, "image/png")
                    entry = {
                        "type": "photo",
                        "media": f"attach://{attach_name}",
                    }
                    if idx == 1:
                        entry["caption"] = f"🃏 <b>{html.escape(date_str)} 모닝 픽 카드뉴스 ({len(card_items)}장)</b>"
                        entry["parse_mode"] = "HTML"
                    media.append(entry)

                try:
                    mg_resp = requests.post(
                        f"https://api.telegram.org/bot{token}/sendMediaGroup",
                        data={"chat_id": cid, "media": json.dumps(media, ensure_ascii=False)},
                        files=files,
                        timeout=45,
                    )
                    if not mg_resp.ok:
                        print(f"[텔레그램] 카드뉴스 앨범 전송 실패 ({cid}): {mg_resp.text}")
                finally:
                    for f_obj in opened:
                        f_obj.close()
            elif len(card_items) == 1 or (lead_chart_path and os.path.exists(lead_chart_path)):
                img_path = card_items[0][2] if card_items else lead_chart_path
                lead_title = picks[0].get("chart_title") or picks[0].get("title", "")
                photo_caption = f"📈 <b>오늘의 대표 카드 ({picks[0].get('broker', '')})</b>\n{html.escape(lead_title)}"
                with open(img_path, "rb") as img_f:
                    p_resp = requests.post(
                        f"https://api.telegram.org/bot{token}/sendPhoto",
                        data={
                            "chat_id": cid,
                            "caption": photo_caption[:1024],
                            "parse_mode": "HTML",
                        },
                        files={"photo": img_f},
                        timeout=30,
                    )
                    if not p_resp.ok:
                        print(f"[텔레그램] 대표 이미지 전송 실패 ({cid}): {p_resp.text}")

            # 2) Pick 1~3 요약 + 원터치 매거진 버튼 메시지 전송
            msg_data = {
                "chat_id": cid,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup:
                msg_data["reply_markup"] = reply_markup

            m_resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=msg_data,
                timeout=20,
            )
            if not m_resp.ok:
                print(f"[텔레그램] 메시지 전송 실패 ({cid}): {m_resp.text}")
                all_ok = False
            else:
                print(f"[텔레그램] 전송 성공 (chat_id={cid})")
        except Exception as e:
            print(f"[텔레그램] 전송 예외 ({cid}): {e}")
            all_ok = False

    return all_ok
