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

def check_stock():
    # 1. 憑證與連線
    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1

    # 2. 直接取得試算表所有二維陣列（避免第2列現金比例干擾）
    all_rows = sheet.get_all_values()
    logger.info(f"試算表總列數: {len(all_rows)}")

    alerts = []
    checked_stocks = []

    # 截圖中股票資料從第 3 列開始（Python index 為 2）
    for row_idx, row in enumerate(all_rows[2:], start=3):
        # 避免空白列或欄位數不足
        if len(row) < 5:
            continue

        # A:代碼(0), B:現價(1), C:名稱(2), D:買點(3), E:賣點(4)
        ticker = row[0].strip()
        price_str = row[1].strip().replace("$", "").replace(",", "")
        buy_str = row[3].strip().replace("$", "").replace(",", "")
        sell_str = row[4].strip().replace("$", "").replace(",", "")

        # 如果股票代碼為空，略過
        if not ticker:
            continue

        try:
            price = float(price_str)
            checked_stocks.append(f"{ticker}({price})")

            buy_val = float(buy_str) if buy_str != "" else None
            sell_val = float(sell_str) if sell_str != "" else None

            if buy_val is not None and price <= buy_val:
                msg = f"🟢 【買入訊號】{ticker} 現價: {price}，已達買點: {buy_val}"
                logger.info(f"🎯 觸發買入: {msg}")
                alerts.append(msg)

            if sell_val is not None and price >= sell_val:
                msg = f"🔴 【賣出訊號】{ticker} 現價: {price}，已達賣點: {sell_val}"
                logger.info(f"🎯 觸發賣出: {msg}")
                alerts.append(msg)

        except ValueError:
            # 略過無法轉為浮點數的列（例如公式報錯或註記文字）
            continue

    logger.info(f"成功讀取的股票清單: {', '.join(checked_stocks)}")

    # 3. 發送邏輯
    if alerts:
        message = "📊 美股監控通知：\n" + "\n".join(alerts)
        send_line_broadcast(message)
    else:
        logger.info("ℹ️ 現價未觸發任何條件。")
        # 💡 除錯測試用：若沒觸發，仍強制發一則狀態回報確認 LINE 暢通
        # 確認收到後，可以把下面兩行註解掉
        test_message = f"🤖 系統連線測試正常！\n已檢查 {len(checked_stocks)} 檔股票，目前未達買賣點位。"
        send_line_broadcast(test_message)

if __name__ == "__main__":
    check_stock()
