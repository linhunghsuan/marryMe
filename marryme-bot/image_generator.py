import json
import os
import io
import logging
import re
import hashlib
import PIL
import gcs_function
import time
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
from google.cloud import storage
from pypinyin import pinyin, Style
# --- 配置 (從環境變數讀取) ---
import os
from collections import Counter

# Google Cloud Storage 設定
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'marryme1140629')

# --- 路徑/檔案配置
GCS_IMAGE_DIR = "generated_seat_maps"
LOGO_IMAGE_GCS_PATH = "LOGO/your_event_logo.png"
BACKGROUND_IMAGE_GCS_PATH = "backgrounds/your_background_image.png"

customer_list_path = "customer_list.json"
table_location_file = "table_locations.json"
DEFAULT_FONT_PATH = "NotoSansTC-Medium.ttf"

# --- 繪圖配置
DEFAULT_IMAGE_BACKGROUND_COLOR = "#fffcf7"
LOGO_AREA_HEIGHT_PX = 150
LOGO_PADDING_PX = 10
IMG_SCALE = 62
IMG_OFFSET_X = 70
IMG_OFFSET_Y_TOP = 30
IMG_OFFSET_Y_TOP_GRID = 60
IMG_OFFSET_Y_BOTTOM = 40
TABLE_RADIUS_PX = int(IMG_SCALE * 0.45)
HIGHLIGHT_THICKNESS_PX = 6
MIN_CANVAS_WIDTH = 480
MIN_CANVAS_HEIGHT = 320

# --- 初始化 ---
customer_list = []
table_locations = {}
customer_name_counts = Counter()
gcs_client = None
bucket = None
IS_LOCAL = False  # 預設為雲端執行

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 初始化函式 ---
def initialize_dependencies(gcs_service_account_path=None, data_dir=None):
    global customer_list, table_locations, customer_name_counts, gcs_client, bucket, customer_list_path
    # 1. 載入資料檔案
    if not data_dir:
        data_dir = os.path.dirname(__file__) # 預設資料檔與此模組在同一目錄
    # 2. 初始化 GCS Client
    try:
        if gcs_service_account_path:
            gcs_client = storage.Client.from_service_account_json(os.path.join(data_dir, gcs_service_account_path))
            IS_LOCAL = True
            logger.info("GCS Client 已從本機金鑰初始化，設定為本機模式。")
        else:
            gcs_client = storage.Client(project=GCP_PROJECT_ID)
            IS_LOCAL = False
            logger.info("GCS Client 使用預設憑證，設定為雲端模式。")

        bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        gcs_function.init_bucket(bucket)  # 注入給 gcs_function 模組
        logger.info(f"成功連接到 GCS Bucket: {GCS_BUCKET_NAME}")
    except Exception as e:
        logger.critical(f"連接 GCS 失敗: {e}", exc_info=True)
        raise

    # 載入賓客名單
    customer_list_path = os.path.join(data_dir, customer_list_path)
    if os.path.exists(customer_list_path):
        try:
            with open(customer_list_path, "r", encoding="utf-8") as f:
                customer_list = json.load(f)
            logger.info(f"成功載入 {len(customer_list)} 位賓客名單。")
            
            # 計算原始中文姓名出現次數
            raw_names = [customer.get("name") for customer in customer_list if customer.get("name")]
            customer_name_counts = Counter(raw_names)
            logger.info(f"賓客姓名計數完成: {len(customer_name_counts)} 個獨立原始姓名。")
        except Exception as e:
            logger.error(f"載入失敗 使用預設的範例賓客名單。", exc_info=True)
            customer_list = [{"name": "王小明", "category": "VIP", "seat": "T1"}]
            customer_name_counts = 1
    else:
        logger.warning(f"賓客名單未找到。")
        customer_list = []
        customer_name_counts = Counter()
    
    # 載入座位表
    table_locations_path = os.path.join(data_dir, table_location_file)
    if os.path.exists(table_locations_path):
        try:
            with open(table_locations_path, "r", encoding="utf-8") as f:
                table_locations = json.load(f)
            logger.info(f"成功載入 ({len(table_locations)} 個桌位資料)。")
        except Exception as e:
            logger.error(f"載入失敗 使用預設的範例桌位資料。", exc_info=True)
            table_locations = {}
    else:
        logger.error(f"桌位資料未找到。")
        table_locations = {}

# --- 檔名生成邏輯 ---
def generate_gcs_safe_ascii_element(text_element):
    if text_element is None:
        text_element = ""
    original_input_str = str(text_element)
    try:
        pinyin_syllables_list = pinyin(original_input_str, style=Style.NORMAL, heteronym=False, errors='replace')
        ascii_text = "".join([item[0] for item in pinyin_syllables_list if item and item[0] and isinstance(item[0], str)])
        ascii_text = ascii_text.lower()
        ascii_text = re.sub(r'[^\w.-]+', '_', ascii_text)
        ascii_text = re.sub(r'_+', '_', ascii_text).strip('_')
        if not ascii_text:
            return hashlib.md5(original_input_str.encode('utf-8')).hexdigest()[:10]
        return ascii_text
    except Exception as e:
        return hashlib.md5(original_input_str.encode('utf-8')).hexdigest()[:10]

def get_gcs_image_path_for_customer(customer_name_original, customer_category_original):
    global customer_name_counts
    customer_name_str = str(customer_name_original)
    customer_category_str = str(customer_category_original if customer_category_original and str(customer_category_original).strip() else "_NO_CATEGORY_")
    pinyin_name_part = generate_gcs_safe_ascii_element(customer_name_str)
    readable_filename_prefix = pinyin_name_part
    log_display_identifier = f"'{customer_name_str}'"
    if customer_name_counts.get(customer_name_str, 0) > 1:
        if customer_category_str != "_NO_CATEGORY_":
            pinyin_category_part = generate_gcs_safe_ascii_element(customer_category_str)
            if pinyin_category_part and pinyin_category_part not in ["unknown", generate_gcs_safe_ascii_element("_NO_CATEGORY_")]:
                readable_filename_prefix = f"{pinyin_name_part}_{pinyin_category_part}"
        log_display_identifier = f"'{customer_name_str}' (分類: '{customer_category_original if customer_category_original else '無'})"
    if not readable_filename_prefix or readable_filename_prefix == "unknown":
        readable_filename_prefix = "guestimage"
    unique_key_for_hash = f"{customer_name_str}::{customer_category_str}" 
    unique_hash_suffix = hashlib.md5(unique_key_for_hash.encode('utf-8')).hexdigest()[:6] 
    final_gcs_filename_base = f"{readable_filename_prefix}_{unique_hash_suffix}"
    image_filename_on_gcs = f"{final_gcs_filename_base}.png"
    return f"{GCS_IMAGE_DIR}/{image_filename_on_gcs}"

# --- 圖片生成邏輯 ---
def create_seat_image(target_seat_id, customer_name, background_alignment="左上角"):
    global table_locations
    """
    產生包含座位、Logo 和可選背景圖的圖片。

    Args:
        target_seat_id (str):目標座位 ID。
        customer_name (str):顧客姓名。
        background_alignment (str): 背景圖片對齊方式。可選值：
                                    "左上角", "右上角", "左下角", "右下角",
                                    "置中", 
                                    "上方置中", "下方置中", "左側置中", "右側置中",
                                    "延展"。
                                    預設為 "右下角"。
    """
    if not table_locations:
        logger.error("table_locations 未載入或為空，無法產生座位圖。")
        return None

    max_x_coord, max_y_coord = 0, 0
    if table_locations:
        all_x = [info["position"][0] for info in table_locations.values() if info and isinstance(info.get("position"), list) and len(info["position"]) > 0]
        all_y = [info["position"][1] for info in table_locations.values() if info and isinstance(info.get("position"), list) and len(info["position"]) > 1]
        if all_x: max_x_coord = max(all_x)
        if all_y: max_y_coord = max(all_y)

    grid_content_width_px = (max_x_coord + 1) * IMG_SCALE
    grid_content_height_px = (max_y_coord + 1) * IMG_SCALE
    canvas_width_px = grid_content_width_px + IMG_OFFSET_X * 2
    canvas_height_px = LOGO_AREA_HEIGHT_PX + IMG_OFFSET_Y_TOP_GRID + grid_content_height_px + IMG_OFFSET_Y_BOTTOM + IMG_OFFSET_Y_TOP
    canvas_width_px = round(max(canvas_width_px, MIN_CANVAS_WIDTH))
    canvas_height_px = round(max(canvas_height_px, MIN_CANVAS_HEIGHT + LOGO_AREA_HEIGHT_PX))

    # 1. 建立基底畫布 (繪製底圖)
    img = Image.new("RGBA", (int(canvas_width_px), int(canvas_height_px)), DEFAULT_IMAGE_BACKGROUND_COLOR)
    logger.info(f"畫布尺寸計算完成：寬度 = {canvas_width_px}px, 高度 = {canvas_height_px}px")

    # 2. 嘗試下載並根據指定的對齊方式貼上背景圖
    background_img_io = gcs_function.download_from_gcs(BACKGROUND_IMAGE_GCS_PATH, save_local=not IS_LOCAL)
    # background_img_io = gcs_function.force_download_from_gcs(BACKGROUND_IMAGE_GCS_PATH)
    if background_img_io:
        try:
            logger.info(f"找到背景圖片 {BACKGROUND_IMAGE_GCS_PATH}，將根據 '{background_alignment}' 進行對齊。")
            background_img = Image.open(background_img_io).convert("RGBA")
            bg_width, bg_height = background_img.size
            
            # 使用 match-case 決定貼上座標
            match background_alignment:
                # 四個角落
                case "左上角":
                    paste_x, paste_y = 0, 0
                case "右上角":
                    paste_x, paste_y = canvas_width_px - bg_width, 0
                case "左下角":
                    paste_x, paste_y = 0, canvas_height_px - bg_height
                case "右下角":
                    paste_x, paste_y = canvas_width_px - bg_width, canvas_height_px - bg_height
                
                # 完全置中
                case "置中":
                    paste_x = (canvas_width_px - bg_width) // 2
                    paste_y = (canvas_height_px - bg_height) // 2

                # 新增的四個邊緣置中選項
                case "上方置中":
                    paste_x = (canvas_width_px - bg_width) // 2
                    paste_y = 0
                case "下方置中":
                    paste_x = (canvas_width_px - bg_width) // 2
                    paste_y = canvas_height_px - bg_height
                case "左側置中":
                    paste_x = 0
                    paste_y = (canvas_height_px - bg_height) // 2
                case "右側置中":
                    paste_x = canvas_width_px - bg_width
                    paste_y = (canvas_height_px - bg_height) // 2

                # 延展
                case "延展":
                    logger.info(f"將背景圖延展以填滿整個畫布 ({canvas_width_px}x{canvas_height_px})。")
                    resized_bg = background_img.resize((canvas_width_px, canvas_height_px), Image.Resampling.LANCZOS)
                    img.paste(resized_bg, (0, 0), resized_bg if resized_bg.mode == 'RGBA' else None)
                    paste_x, paste_y = None, None # 跳過後續的貼上
                
                # 預設/錯誤處理
                case _:
                    logger.warning(f"提供了無效的背景對齊參數。將使用預設的 '左上角' 對齊。")
                    paste_x, paste_y = canvas_width_px - bg_width, canvas_height_px - bg_height

            if paste_x is not None:
                img.paste(background_img, (paste_x, paste_y), background_img)

        except Exception as e:
            logger.error(f"處理背景圖片失敗 ({BACKGROUND_IMAGE_GCS_PATH})，將使用預設背景色。")
    else:
        logger.info(f"未找到背景圖片 {BACKGROUND_IMAGE_GCS_PATH}，將使用預設背景色。")

    # 3. 繪製 LOGO 圖 (維持在上方中央)
    draw = ImageDraw.Draw(img)   
    logo_img_io = gcs_function.download_from_gcs(LOGO_IMAGE_GCS_PATH, save_local=not IS_LOCAL)
    if logo_img_io:
        try:
            logo_original = Image.open(logo_img_io).convert("RGBA")
            logo_available_width = canvas_width_px - (IMG_OFFSET_X + LOGO_PADDING_PX) * 2
            logo_available_height = LOGO_AREA_HEIGHT_PX - LOGO_PADDING_PX * 2
            logo_scaled = logo_original.copy()
            logo_scaled.thumbnail((logo_available_width, logo_available_height), Image.Resampling.LANCZOS)
            logo_paste_x = (canvas_width_px - logo_scaled.width) // 2
            logo_paste_y = IMG_OFFSET_Y_TOP + LOGO_PADDING_PX + (logo_available_height - logo_scaled.height) // 2
            img.paste(logo_scaled, (logo_paste_x, logo_paste_y), logo_scaled)
        except Exception as e:
            logger.error(f"載入或繪製 LOGO 失敗 ({LOGO_IMAGE_GCS_PATH})")
    font_path = os.path.join(os.path.dirname(__file__), DEFAULT_FONT_PATH)
    if not os.path.exists(font_path): 
        logger.warning(f"字型檔案 '{font_path}' 未找到，將使用預設字型。")
        font_path = None 
    try:
        font_large = PIL.ImageFont.truetype(font_path, 28) if font_path else PIL.ImageFont.load_default(size=28)
        font_table_id = PIL.ImageFont.truetype(font_path, 14) if font_path else PIL.ImageFont.load_default(size=14)
        font_table_displayname = PIL.ImageFont.truetype(font_path, 12) if font_path else PIL.ImageFont.load_default(size=12)
        font_prompt_small = PIL.ImageFont.truetype(font_path, 18) if font_path else PIL.ImageFont.load_default(size=18)
    except Exception as e:
        logger.critical(f"載入字型時發生嚴重錯誤", exc_info=True)
        raise

    color_map = {
    "normal":     "#cba6c3",
    "stage":      "#9b8281", 
    "head_table": "#e7ded9",
    "blocked":    "#fffcf7" 
    }
    highlight_color = "#ffdd30"       # 高亮顏色
    highlight_text_color = "#000000"
    text_color_on_table = "#ffffff"   # 桌子上文字的顏色
    text_color_on_table_displayname = "#ffffff" #備用紅色 "#ac4d4d"   # 桌子上文字的顏色
    text_color_prompt = "#000000"     # 底部提示文字的顏色

    grid_drawing_origin_y_pillow = IMG_OFFSET_Y_TOP + LOGO_AREA_HEIGHT_PX + IMG_OFFSET_Y_TOP_GRID

    # 輔助函數 1：繪製多行文字 (作為巢狀函式)
    def draw_multiline_text(center_pos, text, font, fill_color, fill_color_line2=None):
        lines = text.split("\n")
        center_x, center_y = center_pos
        if len(lines) == 1:
            draw.text((center_x, center_y), lines[0], fill=fill_color, font=font, anchor="mm", align="center")
        elif len(lines) == 2:
            line_spacing = 2
            try:
                # Pillow 10.x.x
                _, top, _, bottom = font.getbbox("A")
                h = bottom - top
            except AttributeError:
                # Older Pillow
                w, h = font.getsize("A")
            
            line1_y = center_y - h / 2 - line_spacing
            line2_y = center_y + h / 2 + line_spacing
            second_line_color = fill_color_line2 if fill_color_line2 else fill_color
            draw.text((center_x, line1_y), lines[0], fill=fill_color, font=font, anchor="mm")
            draw.text((center_x, line2_y), lines[1], fill=second_line_color, font=font, anchor="mm")

    # 輔助函數 2：繪製群組形狀 (作為巢狀函式)
    def draw_group_box(items, text, item_type):
        if not items: return
        coords_x = [v['position'][0] for v in items.values()]
        coords_y = [v['position'][1] for v in items.values()]
        min_gx, max_gx = min(coords_x), max(coords_x)
        min_gy, max_gy = max(coords_y), min(coords_y)

        x0 = IMG_OFFSET_X + min_gx * IMG_SCALE
        x1 = IMG_OFFSET_X + (max_gx + 1) * IMG_SCALE
        y0 = grid_drawing_origin_y_pillow + (grid_content_height_px - (min_gy + 1) * IMG_SCALE)
        y1 = grid_drawing_origin_y_pillow + (grid_content_height_px - max_gy * IMG_SCALE)
        bbox = (x0, y0, x1, y1)
        center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2

        is_highlighted = any(item_id == target_seat_id for item_id in items)
        current_color = color_map.get(item_type)
        text_color = highlight_text_color if is_highlighted else text_color_on_table
        
        shape_draw_func = draw.ellipse if item_type == "head_table" else draw.rectangle
        
        if is_highlighted:
            outer_bbox = (bbox[0] - HIGHLIGHT_THICKNESS_PX, bbox[1] - HIGHLIGHT_THICKNESS_PX, 
                          bbox[2] + HIGHLIGHT_THICKNESS_PX, bbox[3] + HIGHLIGHT_THICKNESS_PX)
            shape_draw_func(outer_bbox, fill=highlight_color)

        shape_draw_func(bbox, fill=current_color)
        draw_multiline_text((center_x, center_y), text, font_prompt_small, text_color)

    # --- 開始：群組繪製邏輯 ---
    
    # 1. 將桌位按類型分組
    stage_items = {k: v for k, v in table_locations.items() if v.get("type") == "stage"}
    head_table_items = {k: v for k, v in table_locations.items() if v.get("type") == "head_table"}
    other_items = {k: v for k, v in table_locations.items() if v.get("type") not in ["stage", "head_table"]}

    # 2. 繪製群組（舞台和主桌）
    stage_bbox = draw_group_box(stage_items, "舞台", "stage")
    head_table_bbox = draw_group_box(head_table_items, "主桌", "head_table")

    # 3. 繪製其他獨立項目
    for item_id, info in other_items.items():
        if not (info and isinstance(info.get("position"), list) and len(info["position"]) == 2): continue
        
        grid_x, grid_y = info["position"]
        item_type = info.get("type", "normal")
        center_x = IMG_OFFSET_X + grid_x * IMG_SCALE + IMG_SCALE // 2
        center_y = grid_drawing_origin_y_pillow + (grid_content_height_px - (grid_y * IMG_SCALE + IMG_SCALE // 2))
        
        is_highlighted = (item_id == target_seat_id)
        current_color = color_map.get(item_type)
        radius = TABLE_RADIUS_PX
        bbox = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)

        if is_highlighted:
            outer_bbox = (bbox[0] - HIGHLIGHT_THICKNESS_PX, bbox[1] - HIGHLIGHT_THICKNESS_PX, 
                          bbox[2] + HIGHLIGHT_THICKNESS_PX, bbox[3] + HIGHLIGHT_THICKNESS_PX)
            draw.ellipse(outer_bbox, fill=highlight_color)

        if item_type == "blocked":
            draw.line([(bbox[0]+radius*0.3, bbox[1]+radius*0.3), (bbox[2]-radius*0.3, bbox[3]-radius*0.3)], fill=current_color, width=2)
            draw.line([(bbox[0]+radius*0.3, bbox[3]-radius*0.3), (bbox[2]-radius*0.3, bbox[1]+radius*0.3)], fill=current_color, width=2)
        else: # Normal tables
            draw.ellipse(bbox, fill=current_color)
            text_to_display = f"{item_id}"
            display_name = info.get("displayName", "")
            if display_name:
                text_to_display += f"\n{display_name}"
            
            text_color = highlight_text_color if is_highlighted else text_color_on_table
            text_color_dn = highlight_text_color if is_highlighted else text_color_on_table_displayname
            draw_multiline_text((center_x, center_y), text_to_display, font_table_displayname, text_color, text_color_dn)

    # 4. 繪製底部提示文字
    prompt = f"{customer_name} 您好，您的座位是 {target_seat_id}"
    if target_seat_id not in table_locations: 
        prompt = f"{customer_name} 您好，座位 {target_seat_id} 未在佈局圖中找到。"
    draw.text((canvas_width_px / 2, canvas_height_px - IMG_OFFSET_Y_BOTTOM / 2), prompt, fill=text_color_prompt, font=font_large, anchor="mm")
    
    # --- 結束：儲存並回傳圖片 ---
    image_io = io.BytesIO()
    img.save(image_io, 'PNG')
    image_io.seek(0)
    return image_io