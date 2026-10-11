"""
Module Săn & Tổng Hợp Voucher Shopee Toàn Diện (Voucher Hunter Engine)
CHUẨN SẢN XUẤT: CHỈ NẠP DỮ LIỆU XÁC MINH, KHÔNG SINH MÃ ẢO
"""
import os
import json
from datetime import datetime

def get_comprehensive_voucher_catalog():
    """
    Kho mã giảm giá Shopee từ các nguồn đã xác minh (không sinh mã ảo).
    """
    inbox_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "leak_inbox.json")
    if os.path.exists(inbox_file):
        try:
            with open(inbox_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []
