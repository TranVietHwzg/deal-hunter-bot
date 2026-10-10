import os
from pydantic import BaseModel, Field

class FeatureFlags(BaseModel):
    # Trạng thái các connector sàn
    enable_shopee: bool = True
    enable_lazada: bool = False   # Bật khi có API/Feed hợp lệ
    enable_tiktok: bool = False   # Bật khi có API/Feed hợp lệ

    # Các tính năng nghiệp vụ
    enable_restock_radar: bool = True
    enable_stacking_engine: bool = True
    enable_strict_zero_freeship: bool = True  # Luôn BẬT, không cho phép tắt
    allow_new_user_vouchers: bool = False     # Mặc định cấm mã tân thủ

    # Chống spam cảnh báo
    enable_dedup_cache: bool = True
    dedup_ttl_seconds: int = 1800  # 30 phút

feature_flags = FeatureFlags()
