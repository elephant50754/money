import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDS_JSON_STR = os.environ.get("GOOGLE_CREDS_JSON")

def send_line_broadcast(text):
    """使用 Broadcast API 推播，無需指定特定 User ID"""
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "messages": [{"type": "text", "text": text}]
    }
    resp = requests.post(url, headers=headers, json=data)
    print(f"LINE broadcast status: {resp.status_code}, response: {resp.text}")

def check_stock():
    # 透過 Service Account 金鑰連線 Google Sheets
    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1  # 讀取第一張工作表
    records = sheet.get_all_records()

    alerts = []
    for row in records:
        ticker = row.get("股票代碼 (Ticker)")
        price = row.get("即時股價 (Current Price)")
        buy_target = row.get("買入點位 (Buy Target)")
        sell_target = row.get("賣出點位 (Sell Target)")

        if not ticker or price == "":
            continue

        try:
            price = float(price)
            if buy_target != "" and price <= float(buy_target):
                alerts.append(f"🟢 【買入訊號】{ticker} 現價: {price}，已達買點: {buy_target}")
            if sell_target != "" and price >= float(sell_target):
                alerts.append(f"🔴 【賣出訊號】{ticker} 現價: {price}，已達賣點: {sell_target}")
        except ValueError:
            continue

    if alerts:
        message = "📊 美股監控通知：\n" + "\n".join(alerts)
        send_line_broadcast(message)
    else:
        print("未達提醒條件，無需推播。")

if __name__ == "__main__":
    check_stock()
