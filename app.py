import os
import json
import time
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

SHEET_CACHE = {
    "data": [],
    "last_update": 0
}
CACHE_TTL = 30  # 快取 30 秒

def get_col(row, idx):
    """安全取得欄位字串"""
    if idx < len(row):
        return row[idx].strip()
    return ""

def get_all_sheet_rows():
    """連線 Google Sheets 並抓取全部資料列 (含快取機制)"""
    current_time = time.time()
    if SHEET_CACHE["data"] and (current_time - SHEET_CACHE["last_update"] < CACHE_TTL):
        return SHEET_CACHE["data"]

    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1
    data = sheet.get_all_values()

    SHEET_CACHE["data"] = data
    SHEET_CACHE["last_update"] = current_time
    return data

def reply_line(reply_token, text):
    """回覆 LINE 訊息"""
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    if len(text) > 4500:
        text = text[:4500] + "\n\n...(因訊息篇幅過長，已截斷)..."

    data = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        logger.info(f"LINE Reply 狀態: HTTP {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"LINE Reply 錯誤內容: {resp.text}")
    except Exception as e:
        logger.error(f"發送 LINE 訊息失敗: {e}")

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "running"}), 200

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json(silent=True) or {}
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

        # ==========================================
        # 0. 快速除錯模式：在 LINE 輸入 DEBUG 即可看清欄位對照
        # ==========================================
        if user_msg.upper() == "DEBUG":
            header_row = rows[1] if len(rows) >= 2 else (rows[0] if rows else [])
            first_stock = stock_rows[0] if stock_rows else []
            
            debug_info = ["🔍【試算表欄位索引檢視】"]
            max_cols = max(len(header_row), len(first_stock))
            for i in range(max_cols):
                col_name = chr(65 + i) if i < 26 else f"Col{i}"
                h_val = get_col(header_row, i)
                s_val = get_col(first_stock, i)
                debug_info.append(f"• 索引 [{i}] ({col_name}欄) -> 表頭: [{h_val}] | 範例值: [{s_val}]")

            reply_line(reply_token, "\n".join(debug_info))
            continue

        reply_text = ""

        # ==========================================
        # 1. 處理「買點」按鈕
        # ==========================================
        if user_msg in ["買點", "🎯 買點", "查詢買點"]:
            results = []
            for row in stock_rows:
                ticker = get_col(row, 0)
                price = get_col(row, 1)
                name = get_col(row, 2)
                position_status = get_col(row, 3)
                buy_target = get_col(row, 4)
                sell_target = get_col(row, 5)
                position_pct = get_col(row, 6)
                note = get_col(row, 7)
                action = get_col(row, 8)
                option_exp = get_col(row, 9)

                if ticker and buy_target:
                    pos_pct_display = f"{position_pct}%" if position_pct else "無"
                    card = [
                        f"🟢 【{ticker}】{name} [{position_status or '未分類'}]",
                        f"💲 現價: {price}",
                        f"🎯 買點: {buy_target} | 賣點: {sell_target or '無'}",
                        f"📊 倉位佔比: {pos_pct_display}",
                        f"⚡ 動作: {action or '無'}",
                        f"⏳ 期權時間: {option_exp or '無'}",
                        f"📝 筆記: {note or '無'}"
                    ]
                    results.append("\n".join(card))

            if results:
                reply_text = f"🎯【有設定買點之清單】(共 {len(results)} 檔)：\n\n" + "\n\n─────────────────\n\n".join(results)
            else:
                reply_text = "目前試算表中沒有任何股票設定買點。"

        # ==========================================
        # 2. 處理「賣點」按鈕
        # ==========================================
        elif user_msg in ["賣點", "🔴 賣點", "查詢賣點"]:
            results = []
            for row in stock_rows:
                ticker = get_col(row, 0)
                price = get_col(row, 1)
                name = get_col(row, 2)
                position_status = get_col(row, 3)
                buy_target = get_col(row, 4)
                sell_target = get_col(row, 5)
                position_pct = get_col(row, 6)
                note = get_col(row, 7)
                action = get_col(row, 8)
                option_exp = get_col(row, 9)

                if ticker and sell_target:
                    pos_pct_display = f"{position_pct}%" if position_pct else "無"
                    card = [
                        f"🔴 【{ticker}】{name} [{position_status or '未分類'}]",
                        f"💲 現價: {price}",
                        f"🎯 買點: {buy_target or '無'} | 賣點: {sell_target}",
                        f"📊 倉位佔比: {pos_pct_display}",
                        f"⚡ 動作: {action or '無'}",
                        f"⏳ 期權時間: {option_exp or '無'}",
                        f"📝 筆記: {note or '無'}"
                    ]
                    results.append("\n".join(card))

            if results:
                reply_text = f"🎯【有設定賣點之清單】(共 {len(results)} 檔)：\n\n" + "\n\n─────────────────\n\n".join(results)
            else:
                reply_text = "目前試算表中沒有任何股票設定賣點。"

        # ==========================================
        # 3. 處理「選擇權」按鈕
        # ==========================================
        elif user_msg in ["選擇權", "期權", "⏳ 選擇權", "期權清單"]:
            results = []
            for row in stock_rows:
                ticker = get_col(row, 0)
                price = get_col(row, 1)
                name = get_col(row, 2)
                position_status = get_col(row, 3)
                position_pct = get_col(row, 6)
                note = get_col(row, 7)
                action = get_col(row, 8)
                option_exp = get_col(row, 9)

                if ticker and (option_exp or action):
                    pos_pct_display = f"{position_pct}%" if position_pct else "無"
                    card = [
                        f"⏳ 【{ticker}】{name} [{position_status or '未分類'}]",
                        f"💲 現價: {price}",
                        f"📊 倉位佔比: {pos_pct_display}",
                        f"⚡ 動作: {action or '無'}",
                        f"⏳ 期權時間: {option_exp or '無'}",
                        f"📝 筆記: {note or '無'}"
                    ]
                    results.append("\n".join(card))

            if results:
                reply_text = f"📊【期權清單】(共 {len(results)} 檔)：\n\n" + "\n\n─────────────────\n\n".join(results)
            else:
                reply_text = "目前試算表中沒有任何股票設定期權時間或動作。"

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
                pos_pct_val = get_col(matched, 6)
                pos_pct_str = f"{pos_pct_val}%" if pos_pct_val else "無"
                reply_text = (
                    f"📊 【{get_col(matched, 0)}】{get_col(matched, 2)}\n"
                    f"🏷️ 倉位狀態: {get_col(matched, 3) or '無'}\n"
                    f"💲 現價: {get_col(matched, 1)}\n"
                    f"🎯 買點: {get_col(matched, 4) or '無'} | 賣點: {get_col(matched, 5) or '無'}\n"
                    f"📊 倉位佔比: {pos_pct_str}\n"
                    f"⚡ 動作: {get_col(matched, 8) or '無'}\n"
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
