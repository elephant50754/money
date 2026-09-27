import os
import json
import logging
import requests
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDS_JSON_STR = os.environ.get("GOOGLE_CREDS_JSON")

def get_col(row, idx):
    """安全取得欄位字串"""
    if idx < len(row):
        return row[idx].strip()
    return ""

def get_all_sheet_rows():
    """連線 Google Sheets 並抓取全部資料列"""
    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1
    return sheet.get_all_values()

def reply_line(reply_token, text):
    """回覆 LINE 訊息"""
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    resp = requests.post(url, headers=headers, json=data, timeout=10)
    logger.info(f"LINE Reply 狀態: HTTP {resp.status_code}")

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "running"}), 200

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    events = body.get("events", [])

    for event in events:
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue

        reply_token = event.get("replyToken")
        user_msg = event["message"]["text"].strip()
        logger.info(f"📩 收到指令:【{user_msg}】")

        try:
            rows = get_all_sheet_rows()
            stock_rows = rows[2:] if len(rows) >= 3 else []
        except Exception as e:
            logger.error(f"Google Sheets 讀取失敗: {e}")
            reply_line(reply_token, "⚠️ 讀取試算表資料失敗，請稍後再試。")
            continue

        reply_text = ""

        # ==========================================
        # 1. 處理圖文選單「買點」按鈕 (E欄為買點)
        # ==========================================
        if user_msg == "買點":
            results = []
            for row in stock_rows:
                ticker = get_col(row, 0)
                price = get_col(row, 1)
                name = get_col(row, 2)
                position_type = get_col(row, 3)  # 新增：D 欄倉位
                buy_target = get_col(row, 4)     # 順延至 E 欄

                if ticker and buy_target:
                    type_str = f" [{position_type}]" if position_type else ""
                    results.append(
                        f"🟢 【{ticker}】{name}{type_str}\n"
                        f"   現價: {price} | 買點: {buy_target}"
                    )

            if results:
                reply_text = f"🎯【有設定買點之清單】(共 {len(results)} 檔)：\n\n" + "\n\n".join(results)
            else:
                reply_text = "目前試算表中沒有任何股票設定買點。"

        # ==========================================
        # 2. 處理圖文選單「賣點」按鈕 (F欄為賣點)
        # ==========================================
        elif user_msg == "賣點":
            results = []
            for row in stock_rows:
                ticker = get_col(row, 0)
                price = get_col(row, 1)
                name = get_col(row, 2)
                position_type = get_col(row, 3)  # 新增：D 欄倉位
                sell_target = get_col(row, 5)    # 順延至 F 欄

                if ticker and sell_target:
                    type_str = f" [{position_type}]" if position_type else ""
                    results.append(
                        f"🔴 【{ticker}】{name}{type_str}\n"
                        f"   現價: {price} | 賣點: {sell_target}"
                    )

            if results:
                reply_text = f"🎯【有設定賣點之清單】(共 {len(results)} 檔)：\n\n" + "\n\n".join(results)
            else:
                reply_text = "目前試算表中沒有任何股票設定賣點。"

        # ==========================================
        # 3. 處理圖文選單「選擇權」按鈕 (J欄為期權時間)
        # ==========================================
        elif user_msg == "選擇權":
            results = []
            for row in stock_rows:
                ticker = get_col(row, 0)
                price = get_col(row, 1)
                name = get_col(row, 2)
                position_type = get_col(row, 3)  # 新增：D 欄倉位
                action = get_col(row, 8)         # 順延至 I 欄
                option_exp = get_col(row, 9)     # 順延至 J 欄

                if ticker and option_exp:
                    action_display = f" | 動作: {action}" if action else ""
                    type_str = f" [{position_type}]" if position_type else ""
                    results.append(
                        f"⏳ 【{ticker}】{name}{type_str}\n"
                        f"   現價: {price}{action_display}\n"
                        f"   期權內容: {option_exp}"
                    )

            if results:
                reply_text = f"📊【期權清單】(共 {len(results)} 檔)：\n\n" + "\n\n".join(results)
            else:
                reply_text = "目前試算表中沒有任何股票設定期權時間。"

        # ==========================================
        # 4. 輸入特定股票代碼（如 NKE、SOFI、MCD）
        # ==========================================
        else:
            ticker_query = user_msg.upper()
            matched = None
            for row in stock_rows:
                if get_col(row, 0).upper() == ticker_query:
                    matched = row
                    break

            if matched:
                reply_text = (
                    f"📊 【{get_col(matched, 0)}】{get_col(matched, 2)}\n"
                    f"🏷️ 倉位狀態: {get_col(matched, 3) or '無'}\n"
                    f"💲 現價: {get_col(matched, 1)}\n"
                    f"🎯 買點: {get_col(matched, 4) or '無'} | 賣點: {get_col(matched, 5) or '無'}\n"
                    f"📊 倉位佔比: {get_col(matched, 6)}%\n"
                    f"⚡ 建議動作: {get_col(matched, 8) or '無'}\n"
                    f"⏳ 期權時間: {get_col(matched, 9) or '無'}\n"
                    f"📝 筆記: {get_col(matched, 7) or '無'}"
                )
            else:
                reply_text = (
                    f"查無指令或股票代碼【{user_msg}】。\n\n"
                    f"💡 你可以直接點擊下方選單「買點」、「賣點」、「選擇權」，或直接輸入股票代碼（如 SOFI、MCD）。"
                )

        reply_line(reply_token, reply_text)

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
