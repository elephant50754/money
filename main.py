def send_line_alert(alerts: dict):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("❌ 未設定 LINE_CHANNEL_ACCESS_TOKEN，無法發送推播！")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"📊 【美股持股點位監控測試】",
        f"📅 日期：{today_str}\n"
    ]
    
    # 組合訊息... (略)
    lines.append("🎉 測試成功！這是一則來自 GitHub Actions 的推播訊息。")
    message_text = "\n".join(lines)

    # 使用 Broadcast API：只要有加好友就一定收得到，完全不需要 LINE_USER_ID
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"type": "text", "text": message_text}]
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        print(f"LINE API 回應狀態碼: {resp.status_code}")
        print(f"LINE API 回應內容: {resp.text}")
        if resp.status_code == 200:
            print("✅ LINE 推播發送成功！請檢查手機。")
        else:
            print(f"❌ LINE 發送失敗，錯誤原因: {resp.text}")
    except Exception as e:
        print(f"❌ 連線異常: {e}")
