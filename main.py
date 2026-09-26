def send_line_summary(results: list):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("⚠️ 未偵測到 LINE_CHANNEL_ACCESS_TOKEN，跳過推播。")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 篩選出建議 Sell Put 或 Buy Call 的標的
    sell_puts = [r for r in results if r.get("strategy_tag") == "SELL_PUT"][:5] # 取前5檔
    buy_calls = [r for r in results if r.get("strategy_tag") == "BUY_CALL"][:5]

    lines = [
        f"📊 【美股波動率與策略日報】",
        f"📅 更新日期：{today_str}",
        f"📌 追蹤標的總數：{len(results)} 檔\n"
    ]

    if sell_puts:
        lines.append("🔥 【高 IV 賣方策略 (Sell Put 候選)】")
        for s in sell_puts:
            prem = f" (權利金約 ${s['premium']})" if s.get('premium') else ""
            lines.append(f"• {s['symbol']} | IV: {round(s['iv']*100, 1)}%{prem}")
        lines.append("")

    if buy_calls:
        lines.append("❄️ 【低 IV 買方策略 (Buy Call 候選)】")
        for b in buy_calls:
            lines.append(f"• {b['symbol']} | IV: {round(b['iv']*100, 1)}%")
        lines.append("")

    lines.append("✅ Google 試算表已同步更新完成！")
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
        if resp.status_code == 200:
            print("🎉 LINE 廣播推播發送成功！")
        else:
            print(f"❌ LINE 發送失敗: {resp.text}")
    except Exception as e:
        print(f"❌ LINE 連線錯誤: {e}")
