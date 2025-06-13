import logging
import image_generator
import gcs_function

# 初始化日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # 呼叫共用模組的初始化函式，並傳入本機的服務帳號金鑰路徑
    try:
        # 假設您的金鑰檔和 pre.py 在同一層目錄
        image_generator.initialize_dependencies("marryme-461108-796e200900bb.json")
    except Exception as e:
        logger.critical(f"連接 GCS 失敗: {e}", exc_info=True)
        return
        
    if not image_generator.customer_list:
        logger.error("賓客名單為空，無法繼續。")
        return
    
    for customer in image_generator.customer_list:
        customer_name = customer.get("name")
        seat_id = customer.get("seat")
        category = customer.get("category")
        
        image_gcs_path = image_generator.get_gcs_image_path_for_customer(customer_name, category)
        image_io = image_generator.create_seat_image(seat_id, customer_name, "延展")
        gcs_function.upload_to_gcs(image_io, image_gcs_path, save_local=not image_generator.IS_LOCAL)

if __name__ == "__main__":
    main()