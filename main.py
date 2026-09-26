import os
import io
import json
import time
from datetime import datetime, timezone
import requests
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

def send_line_summary(results: list):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("⚠️ 未偵測到 LINE_CHANNEL_ACCESS_TOKEN，跳過推播。")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    sell_puts = [r for r in results if r.get("strategy_tag") == "SELL_PUT"][:5]
    buy_calls = [r for r in results if r.get("strategy_tag") == "BUY_CALL"][:5]

    lines = [
        "📊 【美股波動率與策略日報】",
        f"📅 更新日期：{today_str}",
        f"📌 追蹤標的總數：{len(results)} 檔\n"
    ]

    if sell_puts:
        lines.append("🔥 【高 IV 賣方策略 (Sell Put 候選)】")
        for s in sell_puts:
            prem = f" (權利金約 ${s['premium']})" if s.get('premium') else ""
            lines.append(f"• {s['symbol']} | IV: {s['iv']}%{prem}")
        lines.append("")

    if buy_calls:
        lines.append("❄️ 【低 IV 買方策略 (Buy Call 候選)】")
        for b in buy_calls:
            lines.append(f"• {b['symbol']} | IV: {b['iv']}%")
        lines.append("")

    if not sell_puts and not buy_calls:
        lines.append("⚡ 今日標的大多處於中性震盪區間，無極端偏高/偏低之波動率標的。")

    message_text = "\n".join(lines)
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json"
    }
    payload = {"messages": [{"type": "text", "text": message_text}]}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        print(f"LINE 回應狀態碼: {resp.status_code}")
        print(f"LINE 回應內容: {resp.text}")
        if resp.status_code == 200:
            print("🎉 LINE 廣播推播發送成功！請檢查手機。")
        else:
            print(f"❌ LINE 發送失敗: {resp.text}")
    except Exception as e:
        print(f"❌ LINE 連線錯誤: {e}")

def get_iv_sample(symbol: str):
    """抓取單一標的 IV 作為範例"""
    try:
        t = yf.Ticker(symbol)
        spot = t.fast_info.get("lastPrice")
        if not spot or not t.options:
            return None
        opt = t.option_chain(t.options[0])
        calls = opt.calls.dropna(subset=['impliedVolatility'])
        if calls.empty:
            return None
        calls['diff'] = (calls['strike'] - spot).abs()
        atm = calls.sort_values('diff').iloc[0]
        iv = round(float(atm['impliedVolatility']) * 100, 1)
        
        tag = "SELL_PUT" if iv >= 50 else ("BUY_CALL" if iv <= 25 else "NEUTRAL")
        return {
            "symbol": symbol,
            "spot": spot,
            "iv": iv,
            "strategy_tag": tag,
            "premium": round(spot * 0.03, 2) if tag == "SELL_PUT" else ""
        }
    except Exception:
        return None

def main():
    # 1. 建立監控標的清單並生成 results
    tickers = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "MSFT", "INTC"]
    print(f"開始抓取標的資料，產生 results 清單 (共 {len(tickers)} 檔)...")
    
    results = []
    for sym in tickers:
        data = get_iv_sample(sym)
        if data:
            results.append(data)
            print(f"成功取得 {sym} | IV: {data['iv']}%")
        time.sleep(0.3)

    print(f"數據處理完成，共取得 {len(results)} 筆有效標的。")

    # 2. 呼叫 LINE 推播
    send_line_summary(results)
    print("全部流程執行完畢！")

if __name__ == "__main__":
    main()
