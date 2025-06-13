import os
import io
import time
import logging

logger = logging.getLogger(__name__)
bucket = None  # 由外部初始化

def init_bucket(external_bucket):
    global bucket
    bucket = external_bucket

def upload_to_gcs(image_io, gcs_path, save_local=False):
    global bucket
    try:
        blob = bucket.blob(gcs_path)
        if save_local:
            local_path = os.path.join("local_backup", os.path.basename(gcs_path))
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                image_io.seek(0)
                f.write(image_io.read())
                image_io.seek(0)

        blob.upload_from_file(image_io, content_type='image/png')
        logger.info(f"圖片已上傳至 GCS: gs://{bucket.name}/{gcs_path}" +
                    (f"，本地備份：{local_path}" if save_local else ""))
        return f"https://storage.googleapis.com/{bucket.name}/{gcs_path}"
    except Exception as e:
        logger.error(f"上傳圖片到 GCS 失败 ({gcs_path}): {e}", exc_info=True)
        return None
    
def force_download_from_gcs(gcs_path):
    from google.cloud import storage
    global bucket
    blob = bucket.blob(gcs_path)
    
    if not blob.exists():
        print(f"[ERROR] blob 不存在: {gcs_path}")
        return None
    
    image_io = io.BytesIO()
    blob.download_to_file(image_io)
    image_io.seek(0)
    
    print(f"[OK] 成功下載: {gcs_path}")
    
    return image_io

def download_from_gcs(gcs_path, save_local=False):
    global bucket
    try:
        blob = bucket.blob(gcs_path)
        if blob.exists():
            image_io = io.BytesIO()
            blob.download_to_file(image_io)
            image_io.seek(0)

            if save_local:
                local_path = os.path.join("local_backup", os.path.basename(gcs_path))
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(image_io.getbuffer())
                logger.info(f"從 GCS 下載並備份至本機：{local_path}")

            return image_io
        else:
            logger.info(f"GCS 檔案不存在: gs://{bucket.name}/{gcs_path}")
            return None
    except Exception as e:
        logger.error(f"從 GCS 下載檔案失敗 ({gcs_path}): {e}", exc_info=True)
        return None

def check_image_exists_gcs(gcs_path):
    try:
        blob = bucket.blob(gcs_path)
        return blob.exists()
    except Exception as e:
        logger.error(f"檢查 GCS 圖片存在性失敗 (gs://{bucket.name}/{gcs_path}): {e}", exc_info=True)
        return False
