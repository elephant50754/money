import os
import json
import time
from datetime import datetime
import requests
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

def get_current_price(symbol: str):
    """取得標的最新股價 (純讀取，不改動試算表)"""
    for _ in range(2):
        try:
            ticker = yf.Ticker(symbol)
            fast_price = ticker.fast_info.get("lastPrice")
            if fast_price and fast_price > 0:
                return round(float(fast_price), 2)
            hist = ticker.history(period="5d")
            if not hist.empty:
                return round(float(hist["Close"].iloc[-1]), 2)
        except Exception:
            time.sleep(0.5)
            continue
    return None

def send_line_alert(alerts: dict):
    """發送自選股監控結果至 LINE"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        print("未設定 LINE 金鑰，略過推播。")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"📊 【自選持股與點位監控】",
        f"📅 監控日期：{today_str}\n"
    ]

    # 1. 達到買入點位 (現價 <= 買入點位)
    if alerts["buy_reached"]:
        lines.append("🟢 【已達買入點位】")
        for item in alerts["buy_reached"]:
            lines.append(f"• {item['symbol']} 現價 ${item['price']} ≤ 買入價 ${item['buy_target']}")
            if item["action"] or item["option_info"]:
                lines.append(f"  └ 策略: {item['action']} ({item['option_info']})")
        lines.append("")

    # 2. 達到賣出點位 (現價 >= 賣出點位)
    if alerts["sell_reached"]:
        lines.append("🔴 【已達賣出目標】")
        for item in alerts["sell_reached"]:
            lines.append(f"• {item['symbol']} 現價 ${item['price']} ≥ 賣出價 ${item['sell_target']}")
        lines.append("")

    # 3. 自選股現價摘要
    if alerts["status_summary"]:
        lines.append("📈 【持股現況清單】")
        for item in alerts["status_summary"]:
            pos_text = f" | 倉位: {item['pos']}%" if item['pos'] else ""
            lines.append(f"• {item['symbol']:<5} 現價: ${item['price']:<7}{pos_text}")

    message_text = "\n".join(lines)

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message_text}]
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        if resp.status_code == 200:
            print("✅ LINE 推播發送成功！")
        else:
            print(f"⚠️ LINE 推播失敗: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"LINE 推播異常: {e}")

def main():
    creds_json_str = os.environ.get("GOOGLE_CREDS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not creds_json_str or not sheet_id:
        print("未設定 Google Sheets 憑證。")
        return

    creds_dict = json.loads(creds_json_str)
    # 宣告唯讀權限，確保絕對不會寫入試算表
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 讀取試算表第一個分頁
    sheet = client.open_by_key(sheet_id).sheet1
    all_data = sheet.get_all_values()

    if len(all_data) < 3:
        print("工作表資料列數不足。")
        return

    # 第 3 列開始為資料列 (Row 3 索引為 2)
    data_rows = all_data[2:]
    
    alerts = {
        "buy_reached": [],
        "sell_reached": [],
        "status_summary": []
    }

    print(f"開始唯讀掃描持股清單 (共 {len(data_rows)} 筆)...")

    for row in data_rows:
        symbol = row[0].strip().upper() if len(row) > 0 else ""
        if not symbol:
            continue

        # 解析目標價與持股資訊
        buy_target = float(row[3]) if len(row) > 3 and row[3].strip() else None
        sell_target = float(row[4]) if len(row) > 4 and row[4].strip() else None
        pos_pct = row[5].strip() if len(row) > 5 else ""
        action = row[7].strip() if len(row) > 7 else ""
        option_info = row[8].strip() if len(row) > 8 else ""

        spot = get_current_price(symbol)
        if spot is not None:
            # 判斷是否碰到買入點位
            if buy_target and spot <= buy_target:
                alerts["buy_reached"].append({
                    "symbol": symbol,
                    "price": spot,
                    "buy_target": buy_target,
                    "action": action,
                    "option_info": option_info
                })

            # 判斷是否碰到賣出點位
            if sell_target and spot >= sell_target:
                alerts["sell_reached"].append({
                    "symbol": symbol,
                    "price": spot,
                    "sell_target": sell_target
                })

            alerts["status_summary"].append({
                "symbol": symbol,
                "price": spot,
                "pos": pos_pct
            })

        time.sleep(0.3)

    print("比對完成，發送 LINE 報告（試算表完全保持原樣，無任何改動）...")
    send_line_alert(alerts)

if __name__ == "__main__":
    main()
