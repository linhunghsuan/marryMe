import json
import os
import pandas as pd

# 假設您的腳本和資料檔案在同一個目錄下
# __file__ 在某些互動式環境中可能未定義，我們做個簡單的處理
try:
    data_dir = os.path.dirname(__file__)
except NameError:
    data_dir = os.getcwd() # 若在 jupyter 或直譯器中執行，則使用當前工作目錄

def json_to_xlsx(json_file, output_file="output.xlsx"):
    """
    將 JSON 檔案轉換為 Excel 檔案。
    能自動偵測 JSON 結構是字典還是列表。
    """
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # --- 新增的邏輯：判斷 JSON 的結構 ---
    if isinstance(data, dict):
        # 保持原有邏輯，處理字典結構的 JSON
        print("偵測到字典 (dictionary) 結構的 JSON，進行轉換...")
        result = []
        for key, value in data.items():
            entry = {
                "table_no": key,
                "position_x": value.get("position", [None, None])[0],
                "position_y": value.get("position", [None, None])[1],
                "type": value.get("type", ""),
                "displayname": value.get("displayName", "")
            }
            result.append(entry)
        df = pd.DataFrame(result)

    elif isinstance(data, list):
        # 新邏輯，處理列表結構的 JSON (例如您的 customer_list.json)
        print("偵測到列表 (list) 結構的 JSON，進行轉換...")
        df = pd.DataFrame(data)

    else:
        print(f"❌ 不支援的 JSON 結構類型：{type(data)}")
        return

    output_path = os.path.join(data_dir, output_file)
    df.to_excel(output_path, index=False)
    print(f"✅ JSON 已成功轉換為 Excel：{output_path}")


def xlsx_to_json(xlsx_file, output_file="output.json"):
    """
    將 Excel 檔案轉換為 JSON 檔案。
    能根據 Excel 欄位自動判斷應輸出為字典結構還是列表結構。
    """
    df = pd.read_excel(xlsx_file)
    # 將 NaN (空值) 替換為空字串，避免匯出時出現 null
    df = df.fillna('')
    columns = set(df.columns)
    
    # 預期的原始格式欄位 (位置資料)
    location_format_cols = {"table_no", "position_x", "position_y"}

    output_data = None

    # --- 新增的邏輯：根據欄位判斷要輸出的 JSON 結構 ---
    if location_format_cols.issubset(columns):
        # 如果包含 'table_no', 'position_x', 'position_y'，則生成字典結構
        print("偵測到「位置」格式的 Excel，轉換為字典結構 JSON...")
        output_data = {}
        for _, row in df.iterrows():
            if not row["table_no"]:  # 跳過 table_no 為空值的行
                continue
            
            key = str(row["table_no"])
            try:
                pos_x = float(row["position_x"])
                pos_y = float(row["position_y"])
            except (ValueError, TypeError):
                pos_x, pos_y = 0.0, 0.0 # 如果轉換失敗給予預設值

            item = {
                "position": [pos_x, pos_y],
                "type": row.get("type", "")
            }
            if "displayname" in columns and row["displayname"]:
                item["displayName"] = row["displayname"]
            output_data[key] = item
    else:
        # 否則，生成列表結構 (適用於客戶名單等一般表格)
        print("偵測到一般表格格式的 Excel，轉換為列表結構 JSON...")
        output_data = df.to_dict(orient='records')
    
    output_path = os.path.join(data_dir, output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)
    print(f"✅ Excel 已成功轉換為 JSON：{output_path}")


# ⛳ 主程式：依副檔名自動判斷要轉換方向
def convert_file(input_file):
    """
    根據副檔名自動調用對應的轉換函式。
    """
    if not os.path.exists(input_file):
        print(f"❌ 錯誤：找不到檔案 '{input_file}'")
        return

    ext = os.path.splitext(input_file)[-1].lower()
    
    if ext == ".json":
        # 決定輸出的 Excel 檔名
        output_filename = os.path.splitext(os.path.basename(input_file))[0] + ".xlsx"
        json_to_xlsx(input_file, output_filename)
    elif ext in [".xls", ".xlsx"]:
        # 決定輸出的 JSON 檔名
        output_filename = os.path.splitext(os.path.basename(input_file))[0] + ".json"
        xlsx_to_json(input_file, output_filename)
    else:
        print("❌ 不支援的檔案格式，請提供 .json, .xls 或 .xlsx 結尾的檔案")

# --- 修改這行以測試您的檔案 ---
# file_name = "table_locations.json"
file_name = "customer_list.json"
# file_name = "customer_list.xlsx" # 您也可以用轉換後的 Excel 檔來反向測試

convert_file(os.path.join(data_dir, file_name))