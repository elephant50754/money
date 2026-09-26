import os
import json
import logging
import traceback
import requests
import gspread
from google.oauth2.service_account import Credentials

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# 讀取環境變數
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDS_JSON_STR = os.environ.get("GOOGLE_CREDS_JSON")

def validate_environment():
    """【階段 1】驗證 Secrets 環境變數是否齊全"""
    logger.info("▶ 正在檢查環境變數...")
    missing = []
    if not LINE_TOKEN:
        missing.append("LINE_CHANNEL_ACCESS_TOKEN")
    if not SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if not CREDS_JSON_STR:
        missing.append("GOOGLE_CREDS_JSON")

    if missing:
        logger.error(f"❌ [環境變數缺少] 未設定以下 Secrets: {', '.join(missing)}")
        return False

    logger.info(f"✅ 環境變數檢查完成 (SHEET_ID: {SHEET_ID[:6]}...{SHEET_ID[-4:]})")
    return True

def send_line_broadcast(text):
    """【階段 4】使用 Broadcast API 推播"""
    logger.info("▶ 正在呼叫 LINE Broadcast API...")
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "messages": [{"type": "text", "text": text}]
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        logger.info(f"LINE API 回應代碼: HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            logger.info("✅ LINE 廣播推播成功！")
        elif resp.status_code == 401:
            logger.error("❌ [LINE 授權失敗] LINE_CHANNEL_ACCESS_TOKEN 無效或過期，請重新確認 Token。")
        elif resp.status_code == 429:
            logger.error("❌ [LINE 額度超限] 本月免費訊息則數已用盡或請求過於頻繁。")
        else:
            logger.error(f"❌ [LINE API 回應錯誤] 回傳內容: {resp.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ [LINE 連線異常] 無法連線至 LINE 伺服器: {str(e)}")

def check_stock():
    # 1. 檢查變數
    if not validate_environment():
        return

    # 2. 連線 Google Sheets
    logger.info("▶ 正在解析 Google 服務帳號憑證...")
    try:
        creds_info = json.loads(CREDS_JSON_STR)
        client_email = creds_info.get("client_email", "未知")
        logger.info(f"Service Account Email: {client_email}")
    except json.JSONDecodeError as e:
        logger.error(f"❌ [憑證格式錯誤] GOOGLE_CREDS_JSON 不是合法的 JSON 格式: {str(e)}")
        return

    try:
        logger.info("▶ 正在授權連線 Google Sheets...")
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        gc = gspread.authorize(credentials)

        logger.info(f"▶ 正在開啟試算表 (ID: {SHEET_ID})...")
        sheet = gc.open_by_key(SHEET_ID).sheet1
        
        logger.info("▶ 正在讀取試算表所有欄位 (get_all_records)...")
        records = sheet.get_all_records()
        logger.info(f"✅ 成功取得資料，共 {len(records)} 列")

    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"❌ [試算表未找到] 找不到 ID: {SHEET_ID}。請檢查試算表 ID 是否正確，並確認是否已將 {client_email} 加入共用（檢視者）。")
        return
    except gspread.exceptions.APIError as e:
        logger.error(f"❌ [Google API 錯誤] 原因: {str(e)}")
        return
    except Exception as e:
        logger.error(f"❌ [Google Sheets 連線未知失敗] 原因: {str(e)}\n{traceback.format_exc()}")
        return

    # 3. 解析與判斷股價條件
    logger.info("▶ 正在比對股票警示點位...")
    alerts = []
    parsed_count = 0

    for idx, row in enumerate(records, start=2):  # start=2 對應 Excel 第 2 列開始
        ticker = row.get("股票代碼 (Ticker)")
        price = row.get("即時股價 (Current Price)")
        buy_target = row.get("買入點位 (Buy Target)")
        sell_target = row.get("賣出點位 (Sell Target)")

        # 略過空代碼或價格未填的列
        if not ticker or price == "":
            continue

        parsed_count += 1
        try:
            price = float(price)
            buy_val = float(buy_target) if buy_target != "" else None
            sell_val = float(sell_target) if sell_target != "" else None

            if buy_val is not None and price <= buy_val:
                msg = f"🟢 【買入訊號】{ticker} 現價: {price}，已達買點: {buy_val}"
                logger.info(f"🎯 觸發條件: {msg}")
                alerts.append(msg)

            if sell_val is not None and price >= sell_val:
                msg = f"🔴 【賣出訊號】{ticker} 現價: {price}，已達賣點: {sell_val}"
                logger.info(f"🎯 觸發條件: {msg}")
                alerts.append(msg)

        except ValueError as e:
            logger.warning(f"⚠️ 第 {idx} 列【{ticker}】數值轉換失敗 (現價: '{price}', 買點: '{buy_target}', 賣點: '{sell_target}')，已略過: {e}")
            continue

    logger.info(f"比對完成：共檢查 {parsed_count} 筆有效股票，觸發 {len(alerts)} 筆警示。")

    # 4. 發送通知
    if alerts:
        message = "📊 美股監控通知：\n" + "\n".join(alerts)
        send_line_broadcast(message)
    else:
        logger.info("ℹ️ 現價未觸發任何買入/賣出點位，無需推播。")

if __name__ == "__main__":
    check_stock()
