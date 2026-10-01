import os
import json
import logging
import requests
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDS_JSON_STR = os.environ.get("GOOGLE_CREDS_JSON")
STATE_FILE = "last_state.json"

def send_line_broadcast_messages(message_list):
    """
    呼叫 LINE Broadcast API。
    LINE 單次呼叫 messages 陣列最多容納 5 則訊息，此處自動以 5 則為單位分批發送。
    """
    if not message_list:
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }

    # 每 5 則訊息切分成一個批次
    chunk_size = 5
    for i in range(0, len(message_list), chunk_size):
        batch = message_list[i:i + chunk_size]
        data = {
            "messages": [{"type": "text", "text": msg} for msg in batch]
        }
        logger.info(f"▶ 正在發送 LINE 廣播 (包含 {len(batch)} 則訊息)...")
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        logger.info(f"LINE API 回應代碼: HTTP {resp.status_code}")
        logger.info(f"LINE API 回應內容: {resp.text}")

def get_col(row, idx):
    if idx < len(row):
        return row[idx].strip()
    return ""

def load_previous_state():
    """讀取上一次儲存的資料狀態"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"讀取舊狀態失敗: {e}")
    return {}

def save_current_state(state):
    """將本次最新資料狀態寫入檔案"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def check_stock():
    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1

    all_rows = sheet.get_all_values()
    previous_state = load_previous_state()
    current_state = {}

    changed_cards = []  # 收集各檔異動卡片

    # 1. 檢查現金比例（G2 與 H2）
    val_g2 = get_col(all_rows[1], 6) if len(all_rows) >= 2 else ""
    val_h2 = get_col(all_rows[1], 7) if len(all_rows) >= 2 else ""
    current_cash = f"{val_g2} ({val_h2})".strip()
    prev_cash = previous_state.get("__CASH_RATIO__", "")
    current_state["__CASH_RATIO__"] = current_cash

    # 若現金比例異動，加入為一個特殊卡片
    if prev_cash and current_cash != prev_cash:
        cash_card = [
            "💰【目標現金比例變更】",
            f"  • 原設定: {prev_cash}",
            f"  • 新調整: {current_cash}"
        ]
        changed_cards.append("\n".join(cash_card))

    # 追蹤欄位（排除 price 現價）
    tracked_fields = {
        "status": "倉位狀態",
        "buy": "買點",
        "sell": "賣點",
        "position": "倉位佔比",
        "action": "動作",
        "option": "期權時間",
        "note": "筆記"
    }

    # 走訪股票資料（從第 3 列開始）
    for row in all_rows[2:]:
        ticker = get_col(row, 0)
        if not ticker:
            continue

        price_str = get_col(row, 1).replace("$", "").replace(",", "")
        name = get_col(row, 2)
        pos_status = get_col(row, 3)                                    # D 欄倉位
        buy_str = get_col(row, 4).replace("$", "").replace(",", "")     # E 欄買點
        sell_str = get_col(row, 5).replace("$", "").replace(",", "")    # F 欄賣點
        position = get_col(row, 6)                                      # G 欄倉位%
        note = get_col(row, 7)                                          # H 欄筆記
        action = get_col(row, 8)                                        # I 欄動作
        option_exp = get_col(row, 9)                                    # J 欄期權時間

        current_data = {
            "name": name,
            "status": pos_status,
            "price": price_str,
            "buy": buy_str,
            "sell": sell_str,
            "position": position,
            "note": note,
            "action": action,
            "option": option_exp
        }
        current_state[ticker] = current_data

        # 比對欄位異動
        change_logs = []
        changed_fields = set()

        if ticker in previous_state:
            prev_data = previous_state[ticker]
            for key, label in tracked_fields.items():
                old_val = prev_data.get(key, "")
                new_val = current_data.get(key, "")

                # 買賣點進行浮點數防呆
                is_changed = False
                if key in ["buy", "sell"] and old_val != "" and new_val != "":
                    try:
                        if float(old_val) != float(new_val):
                            is_changed = True
                    except ValueError:
                        is_changed = (old_val != new_val)
                else:
                    is_changed = (old_val != new_val)

                if is_changed:
                    changed_fields.add(key)
                    change_logs.append(f"  • {label}: {old_val or '無'} ➔ {new_val or '無'}")
        else:
            if previous_state:  # 新增股票代碼
                change_logs.append("  • 新增股票代碼至試算表")

        # 組成單檔卡片
        if change_logs:
            mark = lambda field: " 👈 [已更新]" if field in changed_fields else ""

            status_display = f" [{pos_status}]" if pos_status else ""
            pos_tag = mark("status")
            buy_tag = mark("buy")
            sell_tag = mark("sell")
            position_tag = mark("position")
            action_tag = mark("action")
            option_tag = mark("option")
            note_tag = mark("note")

            card = [
                f"📌 代碼: {ticker} ({name or '未填'}){status_display}{pos_tag}",
                f"📝 異動: \n" + "\n".join(change_logs),
                f"----------------------------",
                f"💲 現價: {price_str or '無'}",
                f"🎯 買點: {buy_str or '無'}{buy_tag} | 賣點: {sell_str or '無'}{sell_tag}",
                f"📊 倉位佔比: {position}%{position_tag}" if position else f"📊 倉位佔比: 無{position_tag}",
                f"⚡ 動作: {action or '無'}{action_tag}",
                f"⏳ 期權時間: {option_exp or '無'}{option_tag}",
                f"📝 筆記: {note or '無'}{note_tag}"
            ]
            changed_cards.append("\n".join(card))

    # 儲存最新狀態檔
    save_current_state(current_state)

    # 2. 合併打包並發送
    if not changed_cards:
        logger.info("ℹ️ 無手動修改資料，不發送通知。")
        return

    logger.info(f"檢測到 {len(changed_cards)} 筆異動，正在組裝合併通知...")

    header = (
        f"🔔【美股持股異動通知】\n"
        f"本次共更新 {len(changed_cards)} 檔標的\n"
        f"═════════════════════════\n"
    )

    # 區塊間使用粗雙線分隔，確保視覺層級清晰
    block_separator = "\n\n═════════════════════════\n\n"
    combined_body = block_separator.join(changed_cards)
    full_text = header + combined_body

    # 防呆：若總字數接近 LINE 5,000 字限制，自動切成多則訊息同時發送
    messages_to_send = []
    if len(full_text) > 4000:
        chunk = header
        for card in changed_cards:
            appended = card + block_separator
            if len(chunk) + len(appended) > 4000:
                messages_to_send.append(chunk.rstrip("\n═"))
                chunk = appended
            else:
                chunk += appended
        if chunk.strip():
            messages_to_send.append(chunk.rstrip("\n═"))
    else:
        messages_to_send.append(full_text)

    # 一次 API 呼叫批次推播
    send_line_broadcast_messages(messages_to_send)
    logger.info("✅ 已完成單次合併推播。")

if __name__ == "__main__":
    check_stock()
