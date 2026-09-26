import os
import json
from datetime import datetime
import requests

def send_line_summary(results: list):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("⚠️ 未偵測到 LINE_CHANNEL_ACCESS_TOKEN，跳過推播。請至 GitHub Secrets 檢查變數名稱！")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 篩選出建議 Sell Put 或 Buy Call 的標的
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
            iv_val = s['iv'] * 100 if s['iv'] < 1.5 else s['iv']
            lines.append(f"• {s['symbol']} | IV: {round(iv_val, 1)}%{prem}")
        lines.append("")

    if buy_calls:
        lines.append("❄️ 【低 IV 買方策略 (Buy Call 候選)】")
        for b in buy_calls:
            iv_val = b['iv'] * 100 if b['iv'] < 1.5 else b['iv']
            lines.append(f"• {b['symbol']} | IV: {round(iv_val, 1)}%")
        lines.append("")

    if not sell_puts and not buy_calls:
        lines.append("⚡ 今日標的大多處於中性震盪區間，無極端偏高/偏低之波動率標的。")

    lines.append("\n✅ Google 試算表已同步更新完成！")
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

# 確保在 main 函式最後呼叫它：
def main():
    # 這裡放你讀取 Google 試算表或抓取 Yahoo 數據的程式碼
    # ...
    # 確保產生了 results 清單
    # ...
    
    # 呼叫推播
    send_line_summary(results)
    print("全部流程執行完畢！")

# 關鍵：這兩行必須在檔案的最底部！
if __name__ == "__main__":
    main()
