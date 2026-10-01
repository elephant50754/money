def get_all_sheet_rows(force_refresh=False):
    """連線 Google Sheets 並抓取全部資料列 (支援強制清除快取)"""
    current_time = time.time()
    
    # 如果不是強制刷新，且快取還在 30 秒內，才使用快取
    if not force_refresh and SHEET_CACHE["data"] and (current_time - SHEET_CACHE["last_update"] < CACHE_TTL):
        return SHEET_CACHE["data"]

    logger.info("🔄 正在向 Google Sheets 請求最新資料（略過快取）...")
    creds_info = json.loads(CREDS_JSON_STR)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1
    data = sheet.get_all_values()

    # 更新快取
    SHEET_CACHE["data"] = data
    SHEET_CACHE["last_update"] = current_time
    return data
