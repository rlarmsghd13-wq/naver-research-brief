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
    picks = payload.get("picks", [])
    if not picks:
        return False

    lines = [f"☀️ <b>{html.escape(date_str)} 네이버 리서치 모닝 픽</b>\n"]
    for idx, p in enumerate(picks, 1):
        broker = html.escape(p.get("broker", ""))
        title = html.escape(p.get("title", ""))
        hook = html.escape(p.get("one_line_hook", ""))
        tag = html.escape(p.get("category_tag", ""))
        lines.append(
            f"<b>{idx}. [{broker}] {title}</b> <i>({tag})</i>\n"
            f"   ➔ {hook}"
        )

    lines.append("\n📊 <i>핵심 차트 확대 · 독해 팁 · 금융 용어 해설은 아래 매거진에서 바로 확인하세요!</i>")
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

    # 대표 차트 이미지 (Pick 1의 첫 번째 차트)
    lead_chart_path = ""
    lead_charts = picks[0].get("charts", [])
    if lead_charts and lead_charts[0].get("url"):
        lead_chart_path = os.path.join(DOCS_DIR, lead_charts[0]["url"])

    all_ok = True
    for cid in chat_ids:
        try:
            # 1) 대표 차트가 있으면 포토 카드 1장 먼저 전송 (간단 캡션)
            if lead_chart_path and os.path.exists(lead_chart_path):
                lead_title = picks[0].get("chart_title") or picks[0].get("title", "")
                photo_caption = f"📈 <b>오늘의 대표 차트 ({picks[0].get('broker', '')})</b>\n{html.escape(lead_title)}"
                with open(lead_chart_path, "rb") as img_f:
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
                        print(f"[텔레그램] 대표 차트 전송 실패 ({cid}): {p_resp.text}")

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
