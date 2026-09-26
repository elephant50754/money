import os
import requests
import pandas as pd

# 從 GitHub Secrets 讀取設定
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")
SHEET_ID = os.environ.get("SPREADSHEET_ID")

def send_line_message(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "to": USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    resp = requests.post(url, headers=headers, json=data)
    print(f"LINE push status: {resp.status_code}")

def check_stock():
    # 匯出第一張工作表為 CSV
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
    
    # 略過前置說明，第 1 欄為標題
    df = pd.read_csv(url, skiprows=0)
    
    # 清理欄位名稱與資料
    df.columns = [str(c).strip() for c in df.columns]
    
    alerts = []
    for _, row in df.iterrows():
        ticker = row.get("股票代碼 (Ticker)")
        price = row.get("即時股價 (Current Price)")
        buy_target = row.get("買入點位 (Buy Target)")
        sell_target = row.get("賣出點位 (Sell Target)")

        if pd.isna(ticker) or pd.isna(price):
            continue

        try:
            price = float(price)
            if pd.notna(buy_target) and price <= float(buy_target):
                alerts.append(f"🟢 【買入訊號】{ticker} 現價: {price}，已達買點: {buy_target}")
            if pd.notna(sell_target) and price >= float(sell_target):
                alerts.append(f"🔴 【賣出訊號】{ticker} 現價: {price}，已達賣點: {sell_target}")
        except ValueError:
            continue

    if alerts:
        message = "📊 美股監控通知：\n" + "\n".join(alerts)
        send_line_message(message)
    else:
        print("未達提醒條件，無需推播。")

if __name__ == "__main__":
    check_stock()
