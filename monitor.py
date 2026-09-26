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
    """安全取得欄位字串，若該儲存格空白或不存在則回傳空字串"""
    if idx < len(row):
        return row[idx].strip()
    return ""

def check_stock():
    # 1. 憑證與連線
    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1

    all_rows = sheet.get_all_values()
    logger.info(f"試算表總列數: {len(all_rows)}")

    # 取得第 2 列的現金比例（截圖中 F2 為 15~20，G2 為 現金比例）
    cash_ratio = ""
    if len(all_rows) >= 2:
        val_f2 = get_col(all_rows[1], 5)
        val_g2 = get_col(all_rows[1], 6)
        if val_f2 or val_g2:
            cash_ratio = f"💰 目標現金比例：{val_f2} ({val_g2})"

    alerts = []
    checked_count = 0

    # 股票資料從第 3 列（Python index 2）開始
    for row in all_rows[2:]:
        ticker = get_col(row, 0)
        price_str = get_col(row, 1).replace("$", "").replace(",", "")
        name = get_col(row, 2)
        buy_str = get_col(row, 3).replace("$", "").replace(",", "")
        sell_str = get_col(row, 4).replace("$", "").replace(",", "")
        position = get_col(row, 5)
        note = get_col(row, 6)
        action = get_col(row, 7)
        option_exp = get_col(row, 8)

        if not ticker:
            continue

        checked_count += 1

        try:
            price = float(price_str)
            buy_val = float(buy_str) if buy_str else None
            sell_val = float(sell_str) if sell_str else None

            signal_type = None
            if buy_val is not None and price <= buy_val:
                signal_type = f"🟢 【買入訊號】達買點: {buy_val}"
            elif sell_val is not None and price >= sell_val:
                signal_type = f"🔴 【賣出訊號】達賣點: {sell_val}"

            if signal_type:
                # 組合 9 個欄位的完整股票資訊區塊
                card = [
                    f"{signal_type}",
                    f"📌 代碼: {ticker} ({name or '未填'})",
                    f"💲 現價: {price}",
                    f"🎯 買點: {buy_str or '無'} | 賣點: {sell_str or '無'}",
                    f"📊 倉位佔比: {position}%" if position else "📊 倉位佔比: 無",
                    f"⚡ 建議動作: {action or '無'}",
                    f"⏳ 期權時間: {option_exp or '無'}",
                    f"📝 筆記: {note or '無'}",
                    "─────────────────"
                ]
                alerts.append("\n".join(card))

        except ValueError:
            continue

    logger.info(f"檢查完成：共比對 {checked_count} 檔，觸發 {len(alerts)} 筆警示。")

    # 組合最終推播訊息
    if alerts:
        header_parts = ["🔔【美股即時更新推播】"]
        if cash_ratio:
            header_parts.append(cash_ratio)
        header_parts.append("─────────────────")

        header = "\n".join(header_parts) + "\n"
        full_message = header + "\n".join(alerts)

        send_line_broadcast(full_message)
    else:
        logger.info("ℹ️ 未達提醒條件，無需推播。")

if __name__ == "__main__":
    check_stock()
