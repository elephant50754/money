def send_line_alert(alerts: dict):
    """使用 Broadcast 群發推播（完全不需要 LINE_USER_ID，只要是好友都會收到）"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("未設定 LINE_CHANNEL_ACCESS_TOKEN，略過推播。")
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

    # 關鍵差異：使用 broadcast 端點，免帶任何 "to" (User ID)
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"type": "text", "text": message_text}]
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        if resp.status_code == 200:
            print("✅ LINE Broadcast 廣播推播發送成功！")
        else:
            print(f"⚠️ LINE 推播失敗: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"LINE 推播異常: {e}")
