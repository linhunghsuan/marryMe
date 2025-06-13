from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest
from linebot.v3.messaging.models import TextMessage, ImageMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import image_generator
import logging
import os
import re
import time
import gcs_function
# 初始化日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')
logger = logging.getLogger(__name__)
# --- 初始化 Flask App 和 LINE Bot ---
app = Flask(__name__)
CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'YOUR_CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_CHANNEL_ACCESS_TOKEN')
try:
    line_config = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    line_bot_api = MessagingApi(ApiClient(line_config))
    handler = WebhookHandler(CHANNEL_SECRET)
except Exception as e:
    logging.critical(f"初始化 LINE SDK 失敗: {e}")
    
# --- 初始化共用模組 ---
try:
    image_generator.initialize_dependencies()
except Exception as e:
    logging.critical("共用模組初始化失敗，應用程式可能無法正常運作！")
    exit(1)

# --- LINE Bot 邏輯函式 ---
def find_customers_by_name(name_query):
    name_query_lower = name_query.lower()
    return [customer for customer in image_generator.customer_list if customer.get("name", "").lower() == name_query_lower]

def find_customer_by_name_and_category(name_query, category_query, customer_options): # 查詢時使用原始中文名
    name_query_lower = name_query.lower()
    category_query_lower = category_query.lower() if category_query else ""
    for cust in customer_options:
        cust_category_lower = cust.get("category", "").lower() if cust.get("category") else ""
        if cust.get("name", "").lower() == name_query_lower and cust_category_lower == category_query_lower:
            return cust
    return None

def send_seat_image_to_line(reply_token, customer_data, force_regenerate=False):
    customer_name_original = customer_data.get("name")
    customer_category_original = customer_data.get("category")
    target_seat_id = customer_data.get("seat")

    if not customer_name_original or not target_seat_id:
        logger.error(f"缺少賓客姓名或座位ID: name={customer_name_original}, seat={target_seat_id}")
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="查詢資料不完整，無法處理。")])
        )
        return

    image_gcs_path = image_generator.get_gcs_image_path_for_customer(customer_name_original, customer_category_original)
    image_url = None
    logger.info(f"處理請求: 賓客='{customer_name_original}', 分類='{customer_category_original if customer_category_original else '無'}', 座位='{target_seat_id}'. GCS 路徑='{image_gcs_path}'")

    if not force_regenerate and gcs_function.check_image_exists_gcs(image_gcs_path):
        timestamp = int(time.time())
        image_url = f"https://storage.googleapis.com/{image_generator.GCS_BUCKET_NAME}/{image_gcs_path}?cache_bust={timestamp}"
        logger.info(f"使用 GCS 圖片: {image_url} (GCS 路徑: {image_gcs_path})")
    else:
        log_reason = "強制重新生成" if force_regenerate else "快取未命中"
        logger.info(f"{log_reason}，為 '{customer_name_original}' (分類:'{customer_category_original if customer_category_original else '無'}', 座位:'{target_seat_id}') 產生新圖片。")

        if target_seat_id not in image_generator.table_locations:
            logger.warning(f"請求的座位ID '{target_seat_id}' 在 table_locations.json 中不存在。")

        image_io = image_generator.create_seat_image(target_seat_id, customer_name_original)
        if image_io:
            gcs_function.upload_to_gcs(image_io, image_gcs_path)
            timestamp = int(time.time())
            image_url = f"https://storage.googleapis.com/{image_generator.GCS_BUCKET_NAME}/{image_gcs_path}?cache_bust={timestamp}"
        else:
            logger.error(f"為 '{customer_name_original}' (座位:'{target_seat_id}') 產生座位圖失敗。")
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="抱歉，為您產生座位圖時發生錯誤。")])
            )
            return

    if image_url:
        if not image_url.startswith("https://"):
            logger.error(f"產生的圖片 URL '{image_url}' 不是 HTTPS。無法發送。")
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="抱歉，圖片連結錯誤，無法顯示。")])
            )
            return
        try:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[ImageMessage(original_content_url=image_url, preview_image_url=image_url)]
                )
            )
            logger.info(f"圖片已成功發送給 '{customer_name_original}'.")
        except Exception as e:
            logger.error(f"透過 LINE 發送圖片失敗 ({image_url}): {e}")
            try:
                line_bot_api.reply_message(
                    ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="抱歉，發送座位圖時遇到問題，請稍後再試。")])
                )
            except Exception as inner_e:
                logger.error(f"回覆錯誤訊息給使用者也失敗: {inner_e}")
    else:
        logger.error(f"最終無法獲取 '{customer_name_original}' (座位:'{target_seat_id}') 的圖片 URL。")
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="抱歉，無法取得您的座位圖，請聯繫服務人員。")])
        )

    
# --- Flask App 路由與 Webhook 處理 ---
user_state = {}

@app.route('/')
def home():
    return "LINE Bot for Seat Assignment (MarryMe) is running!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent): 
    user_id = event.source.user_id
    text = event.message.text.strip()
    reply_token = event.reply_token
    
    logger.info(f"接收到來自 user_id: {user_id} 的訊息: '{text}'")

    # 用戶狀態鍵
    user_context_key_options = (user_id, "disambiguation_options") # 用於常規查詢的多選項
    user_context_key_regen = (user_id, "regenerate_options") # 用於重新生成的多選項

    # 優先處理重新生成指令
    if text.lower().startswith("重新生成_") or text.lower().startswith("regenerate_"):
        command_parts = text.split("_", 1)
        if len(command_parts) < 2 or not command_parts[1]:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="重新生成指令格式錯誤。\n請輸入：\n重新生成_姓名\n或\n重新生成_姓名_分類")]))
            return
        
        query_content = command_parts[1]
        name_to_process_orig = ""
        category_to_process_orig = None

        # 解析 "姓名_分類" 或僅 "姓名"
        # 這裡的邏輯是，如果 query_content 中有底線，則優先嘗試將其分割為姓名和分類
        # 並驗證這個分割出的分類是否是該姓名的一個已知分類
        if "_" in query_content:
            potential_name, _, potential_category = query_content.rpartition("_") # 從右邊分割，處理名字本身可能含有的底線
            # 檢查 potential_name 是否有效，以及 potential_category 是否真的是一個分類
            temp_customers_for_check = find_customers_by_name(potential_name)
            customer_check = find_customer_by_name_and_category(potential_name, potential_category, temp_customers_for_check)
            if customer_check:
                name_to_process_orig = potential_name
                category_to_process_orig = potential_category
            else: # 分割出的不是有效分類，或姓名不對，則將整個 query_content 視為姓名
                name_to_process_orig = query_content
        else:
            name_to_process_orig = query_content
        
        logger.info(f"重新生成請求: 姓名='{name_to_process_orig}', 分類='{category_to_process_orig if category_to_process_orig else '無'}'")
        
        target_customers_for_regen = []
        if name_to_process_orig:
            matching_by_name = find_customers_by_name(name_to_process_orig)
            if category_to_process_orig is not None:
                customer = find_customer_by_name_and_category(name_to_process_orig, category_to_process_orig, matching_by_name)
                if customer:
                    target_customers_for_regen = [customer]
                else:
                    line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"找不到賓客 '{name_to_process_orig}' (分類: {category_to_process_orig if category_to_process_orig else '無'}) 可重新生成。")]))
                    return
            else: # 指令中未給分類
                target_customers_for_regen = matching_by_name
        
        if not target_customers_for_regen:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"找不到賓客 '{name_to_process_orig}' 的資料可重新生成。")]))
            return

        if len(target_customers_for_regen) == 1:
            customer_data = target_customers_for_regen[0]
            logger.info(f"找到賓客進行重新生成: {customer_data['name']} (分類: {customer_data.get('category', '無')})")
            send_seat_image_to_line(reply_token, customer_data, force_regenerate=True)
            if user_context_key_options in user_state: del user_state[user_context_key_options]
            if user_context_key_regen in user_state: del user_state[user_context_key_regen]
        else: # 多個匹配，需要選擇 (即使是重新生成指令)
            options_text = [f"{idx+1}. {cust['name']} ({cust.get('category','無')})" for idx, cust in enumerate(target_customers_for_regen)]
            reply_msg = "偵測到多位符合條件的賓客，請選擇您要重新生成哪一位的座位圖 (請回覆數字或完整選項)：\n" + "\n".join(options_text)
            user_state[user_context_key_regen] = target_customers_for_regen
            if user_context_key_options in user_state: del user_state[user_context_key_options]
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=reply_msg)]))
        return # 重新生成指令處理結束

    # 處理來自「重新生成」的選項回覆
    if user_context_key_regen in user_state:
        options = user_state.pop(user_context_key_regen)
        selected_customer = None
        try:
            if text.isdigit() and 1 <= int(text) <= len(options):
                selected_customer = options[int(text)-1]
            else:
                for cust in options:
                    # 考慮多種匹配方式
                    name = cust["name"]
                    category = cust.get("category", "") # 用 get 避免 KeyError
                    category_display = category if category else "無" # 顯示時用"無"
                    
                    if text.lower() == f"{name} ({category_display})".lower() or \
                        text.lower() == f"{name}（{category_display}）".lower() or \
                        (not category and text.lower() == name.lower()): # 如果選項沒分類且輸入也沒分類
                        selected_customer = cust
                        break
        except ValueError: 
            pass
        
        if selected_customer:
            logger.info(f"使用者從『重新生成』選項中選擇了: {selected_customer['name']} (分類: {selected_customer.get('category','無')})")
            send_seat_image_to_line(reply_token, selected_customer, force_regenerate=True)
        else:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="無效的選擇。請重新發起『重新生成』指令。")]))
        return

    # 處理來自「常規查詢」的選項回覆
    if user_context_key_options in user_state:
        options = user_state.pop(user_context_key_options)
        selected_customer = None
        try:
            if text.isdigit() and 1 <= int(text) <= len(options):
                selected_customer = options[int(text)-1]
            else:
                for cust in options:
                    name = cust["name"]
                    category = cust.get("category", "")
                    category_display = category if category else "無"

                    if text.lower() == f"{name} ({category_display})".lower() or \
                        text.lower() == f"{name}（{category_display}）".lower() or \
                        (not category and text.lower() == name.lower()):
                        selected_customer = cust
                        break
        except ValueError:
            pass
            
        if selected_customer:
            logger.info(f"使用者從選項中選擇了: {selected_customer['name']} (分類: {selected_customer.get('category','無')})")
            send_seat_image_to_line(reply_token, selected_customer, force_regenerate=False)
        else:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="無效的選擇。請重新輸入您的姓名。")]))
        return

    # --- 一般查詢流程 (非選項回覆，非重新生成指令) ---
    # 嘗試解析輸入 "姓名 (分類)" 或 "姓名（分類）" 或 "姓名"
    potential_name_orig = text # 預設整個輸入為姓名
    potential_category_orig = None # 預設無分類
    
    # 解析常見的 "姓名 (分類)" 模式
    match_parentheses = re.match(r"^(.*?)\s*[(（](.+?)[)）]\s*$", text)
    if match_parentheses:
        potential_name_orig = match_parentheses.group(1).strip()
        potential_category_orig = match_parentheses.group(2).strip()
        logger.info(f"解析輸入為: 姓名='{potential_name_orig}', 分類='{potential_category_orig}'")
    else:
        logger.info(f"未解析出明確分類，將 '{text}' 整體視為姓名或進行模糊匹配。")

    found_customers = []
    if potential_name_orig: # 確保 potential_name_orig 不是空的
        # 先嘗試精確匹配 (姓名 + 分類，如果分類被解析出來)
        if potential_category_orig is not None: # 即使是空字串也算解析出分類意圖
            all_with_name = find_customers_by_name(potential_name_orig)
            customer = find_customer_by_name_and_category(potential_name_orig, potential_category_orig, all_with_name)
            if customer:
                found_customers = [customer]
        
        # 如果精確 (姓名+分類) 找不到，或者一開始就沒有分類，則只用姓名查找
        if not found_customers:
            found_customers = find_customers_by_name(potential_name_orig) # 如果上面沒解析出分類，這裡的 potential_name_orig 就是原始 text

    if not found_customers:
        logger.info(f"找不到賓客: '{text}'")
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"抱歉，找不到與 '{text}' 相符的賓客資訊。請確認輸入是否正確，或嘗試僅輸入姓名。")])
        )
    elif len(found_customers) == 1:
        customer_data = found_customers[0]
        logger.info(f"找到唯一賓客: {customer_data['name']} (分類: {customer_data.get('category', '無')})")
        send_seat_image_to_line(reply_token, customer_data, force_regenerate=False)
    else: # 找到多個同名（但可能不同分類）的賓客
        logger.info(f"找到多位名為 '{potential_name_orig}' 的賓客，要求用戶選擇。")
        options_text = [f"{idx+1}. {cust['name']} ({cust.get('category','無')})" for idx, cust in enumerate(found_customers)]
        reply_msg = "我們找到了幾位符合條件的賓客，請問您是哪一位？ (請回覆數字或完整選項)：\n" + "\n".join(options_text)
        user_state[user_context_key_options] = found_customers # 存儲待選列表
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=reply_msg)]))

if __name__ == "__main__":
    if not image_generator.customer_list:
        logger.warning("警告：賓客名單為空。Bot 可能無法正常處理查詢。")
    if not image_generator.table_locations:
        logger.warning("警告：桌位佈局為空。無法產生座位圖。")

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)