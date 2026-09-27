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

def send_line_broadcast(text):
    logger.info("▶ 正在呼叫 LINE Broadcast API...")
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "messages": [{"type": "text", "text": text}]
    }
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

    # 取得現金比例（G2 與 H2）
    val_g2 = get_col(all_rows[1], 6) if len(all_rows) >= 2 else ""
    val_h2 = get_col(all_rows[1], 7) if len(all_rows) >= 2 else ""
    current_cash = f"{val_g2} ({val_h2})".strip()
    prev_cash = previous_state.get("__CASH_RATIO__", "")
    current_state["__CASH_RATIO__"] = current_cash

    alerts = []

    # 現金比例有更動時推播
    if prev_cash and current_cash != prev_cash:
        alerts.append(f"🔄 【目標現金比例變更】\n舊值: {prev_cash} ➔ 新值: {current_cash}\n─────────────────")

    # 包含現價在內的比對清單
    field_names = {
        "price": "現價",
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

        # 1. 判斷是否有內容更動（例如：價格 20 ➔ 30）
        change_logs = []
        changed_fields = set()
        
        if ticker in previous_state:
            prev_data = previous_state[ticker]
            for key, label in field_names.items():
                old_val = prev_data.get(key, "")
                new_val = current_data.get(key, "")
                
                # 若為價格/點位，進行浮點數防呆比對（避免 20 與 20.0 誤判）
                is_changed = False
                if key in ["price", "buy", "sell"] and old_val != "" and new_val != "":
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

        # 2. 判斷現價是否達到買賣點位
        signal_type = None
        try:
            price = float(price_str)
            buy_val = float(buy_str) if buy_str else None
            sell_val = float(sell_str) if sell_str else None

            if buy_val is not None and price <= buy_val:
                signal_type = f"🟢 【買入訊號】達買點: {buy_val}"
            elif sell_val is not None and price >= sell_val:
                signal_type = f"🔴 【賣出訊號】達賣點: {sell_val}"
        except ValueError:
            pass

        # 3. 滿足條件時打包訊息
        if change_logs or signal_type:
            status_tags = []
            if signal_type:
                status_tags.append(signal_type)
            if change_logs:
                status_tags.append("📝 【資料內容更新】\n" + "\n".join(change_logs))

            status_display = f" [{pos_status}]" if pos_status else ""
            
            # 若為欄位內容更新，在下方欄位特別加上標註提醒
            price_display = f"{price_str or '無'}"
            buy_display = f"{buy_str or '無'}"
            sell_display = f"{sell_str or '無'}"
            
            card = [
                "\n".join(status_tags),
                f"📌 代碼: {ticker} ({name or '未填'}){status_display}",
                f"💲 現價: {price_display}",
                f"🎯 買點: {buy_display} | 賣點: {sell_display}",
                f"📊 倉位佔比: {position}%" if position else "📊 倉位佔比: 無",
                f"⚡ 動作: {action or '無'}",
                f"⏳ 期權時間: {option_exp or '無'}",
                f"📝 筆記: {note or '無'}",
                "─────────────────"
            ]
            alerts.append("\n".join(card))

    # 儲存最新狀態
    save_current_state(current_state)

    # 4. 發送通知
    if alerts:
        header = f"🔔【美股即時更新推播】\n💰 目標現金比例：{current_cash}\n─────────────────\n"
        full_message = header + "\n".join(alerts)
        send_line_broadcast(full_message)
    else:
        logger.info("ℹ️ 無手動修改資料或達到買賣點位，不推播。")

if __name__ == "__main__":
    check_stock()
