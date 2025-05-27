from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, ImageSendMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from PIL import Image, ImageDraw, ImageFont
import io
import os

# 你的 Channel secret 和 Channel access token
channel_secret = '967524b34b7e8566c30bc4522bbb55a0'
channel_access_token = 's83m4CfnZmIJ2DX45T+0o3J7oJDGo4Otq++7iFH2KBjmrGrLKgWs9gWmzhWwfnsCB5Kou1RHW1LbSGpnCdcDDjN4LNI6MZzzqbp6J6pGrvkW2fMKqsoaap0UZNULcEHN/MI5cWW5p465Dom3RrxKDAdB04t89/1O/w1cDnyilFU='

# LINE Bot API 設定
configuration = Configuration(access_token=channel_access_token)
line_bot_api = MessagingApi(ApiClient(configuration))
handler = WebhookHandler(channel_secret)

# 模擬客人清單 (你需要替換成你的實際資料來源)
customer_list = [
    {"name": "王小明", "category": "VIP", "seat": "A1"},
    {"name": "李小華", "category": "一般", "seat": "B2"},
    {"name": "王小明", "category": "學生", "seat": "C3"},
    {"name": "陳大同", "category": "VIP", "seat": "A2"},
]

# 用戶狀態暫存 (用於處理相同名字的客人)
user_state = {}

app = Flask(__name__)

def create_seat_image(seat_number, customer_name):
    """根據座位號碼和客人姓名產生座位示意圖"""
    try:
        # 創建一個新的圖片
        img_width = 400
        img_height = 300
        img = Image.new('RGB', (img_width, img_height), color='lightgray')
        d = ImageDraw.Draw(img)

        # 設定字體 (你需要確認字體檔案是否存在)
        try:
            font = ImageFont.truetype("arial.ttf", 40) # 嘗試使用 Arial
        except IOError:
            font = ImageFont.load_default() # 使用預設字體

        # 繪製座位號碼
        text_seat = f"座位: {seat_number}"
        textwidth_seat, textheight_seat = d.textlength(text_seat, font=font)
        text_x_seat = (img_width - textwidth_seat) // 2
        text_y_seat = 50
        d.text((text_x_seat, text_y_seat), text_seat, fill=(0, 0, 0), font=font)

        # 繪製客人姓名
        text_name = f"姓名: {customer_name}"
        textwidth_name, textheight_name = d.textlength(text_name, font=font)
        text_x_name = (img_width - textwidth_name) // 2
        text_y_name = 150
        d.text((text_x_name, text_y_name), text_name, fill=(0, 0, 0), font=font)

        # 將圖片轉換為 BytesIO 物件
        image_io = io.BytesIO()
        img.save(image_io, 'png')
        image_io.seek(0)
        return image_io
    except Exception as e:
        print(f"產生圖片時發生錯誤: {e}")
        return None

def find_customers_by_name(name):
    """根據姓名在客人清單中尋找客人"""
    return [customer for customer in customer_list if customer["name"] == name]

@app.route("/callback", methods=['POST'])
def callback():
    """LINE Bot 的 Webhook 接收處理"""
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if user_id not in user_state:
        user_state[user_id] = {}

    if "waiting_for_category" in user_state[user_id] and user_state[user_id]["waiting_for_category"]:
        category = text
        name_to_find = user_state[user_id].get("pending_name")
        if name_to_find:
            matching_customer = next((c for c in find_customers_by_name(name_to_find) if c["category"] == category), None)
            if matching_customer:
                image_io = create_seat_image(matching_customer["seat"], matching_customer["name"])
                if image_io:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[ImageSendMessage(original_content_url='https://example.com/static/seat.png',  # 你需要上傳圖片並提供網址
                                                       preview_image_url='https://example.com/static/seat_preview.png')] # 同上
                        )
                    )
                    # 實際發送圖片訊息 (需要將 BytesIO 轉換為可上傳的格式)
                    # 這部分需要更詳細的 LINE Bot SDK 圖片發送處理
                    # 你可能需要將圖片儲存到伺服器，然後提供 URL

                    del user_state[user_id]["waiting_for_category"]
                    del user_state[user_id]["pending_name"]
                else:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="抱歉，產生座位示意圖失敗。")]
                        )
                    )
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"找不到 {name_to_find} 中分類為 {category} 的客人。")]
                    )
                )
                del user_state[user_id]["waiting_for_category"]
                del user_state[user_id]["pending_name"]
        else:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="發生錯誤，請重新輸入姓名。")]
                )
            )
            del user_state[user_id]["waiting_for_category"]
            del user_state[user_id]["pending_name"]
        return

    matching_customers = find_customers_by_name(text)

    if not matching_customers:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"找不到名為 {text} 的客人。")]
            )
        )
    elif len(matching_customers) == 1:
        customer = matching_customers[0]
        image_io = create_seat_image(customer["seat"], customer["name"])
        if image_io:
            # 準備圖片訊息
            # 需要將 image_io 上傳到某個地方，並取得可公開存取的 URL
            # 或者使用 LINE Bot SDK 提供的更直接的方式發送圖片 (如果有的話)

            # 這裡先用一個靜態的範例 URL，你需要替換成你實際的圖片 URL
            image_url = 'https://via.placeholder.com/400x300' # 替換成你的圖片 URL
            preview_url = 'https://via.placeholder.com/200x150' # 替換成你的預覽圖 URL

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[ImageSendMessage(original_content_url=image_url,
                                               preview_image_url=preview_url)]
                )
            )
        else:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="抱歉，產生座位示意圖失敗。")]
                )
            )
    else:
        # 有多個相同名字的客人，詢問子分類
        categories = list(set(c["category"] for c in matching_customers))
        question = f"找到多個名為 {text} 的客人，請問您的分類是？\n"
        question += "\n".join([f"- {cat}" for cat in categories])

        user_state[user_id]["waiting_for_category"] = True
        user_state[user_id]["pending_name"] = text

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=question)]
            )
        )

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))