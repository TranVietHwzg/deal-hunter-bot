import pytest
import sqlite3
import os
from app.core.junk_filter import is_freeship, validate_voucher, FREESHIP_EXCLUSION_PATTERN

def test_freeship_pattern_matching():
    freeship_samples = [
        "Mã Freeship 0đ toàn sàn",
        "Free shipping toàn quốc cho đơn từ 0đ",
        "Voucher miễn phí vận chuyển 30k",
        "Hỗ trợ phí vận chuyển đơn hàng Shopee",
        "Giảm 100% tiền ship đơn từ 50k",
        "Voucher ship 0đ khung giờ vàng",
        "Giao hàng 0đ cho mọi đơn hàng",
        "Mã trợ giá ship tối đa 20k",
        "Shipping fee subsidy 50k"
    ]
    for sample in freeship_samples:
        assert FREESHIP_EXCLUSION_PATTERN.search(sample) is not None, f"Failed to match freeship pattern on: {sample}"

def test_is_freeship_exclusion():
    # 1. Type chứa SHIP
    v1 = {"voucher_type": "FREESHIP_EXTRA", "title": "Giảm 15k"}
    is_ship, reason = is_freeship(v1)
    assert is_ship is True
    assert "vận chuyển" in reason.lower()

    # 2. discount_target là shipping_fee
    v2 = {"voucher_type": "PLATFORM", "discount_target": "shipping_fee", "title": "Mã giảm giá"}
    is_ship, reason = is_freeship(v2)
    assert is_ship is True

    # 3. Tiêu đề hoặc mô tả chứa freeship
    v3 = {"voucher_type": "PLATFORM", "title": "Giảm 30k Phí Vận Chuyển"}
    is_ship, reason = is_freeship(v3)
    assert is_ship is True

    # 4. Voucher sản phẩm thực (KHÔNG PHẢI FREESHIP) -> Phải trả về False
    v4 = {
        "voucher_type": "PLATFORM",
        "title": "Giảm 100k đơn từ 500k toàn sàn Điện Tử",
        "description": "Áp dụng cho mọi sản phẩm công nghệ",
        "voucher_code": "TECH100K",
        "discount_target": "product_price"
    }
    is_ship, _ = is_freeship(v4)
    assert is_ship is False

def test_validate_voucher_rejects_freeship_and_junk():
    # Voucher freeship
    v_ship = {"voucher_type": "FREESHIP", "title": "Free ship", "discount_value": 30000}
    is_valid, reason = validate_voucher(v_ship)
    assert is_valid is False
    assert "TRẢM FREESHIP" in reason

    # Voucher tân thủ khi allow_new_user=False
    v_new = {"voucher_type": "PLATFORM", "title": "Giảm 50k", "discount_value": 50000, "is_new_user_only": True}
    is_valid, reason = validate_voucher(v_new, allow_new_user=False)
    assert is_valid is False
    assert "mới" in reason

    # Voucher hết hạn
    v_expired = {"voucher_type": "PLATFORM", "title": "Giảm 50k", "discount_value": 50000, "status": "EXPIRED"}
    is_valid, reason = validate_voucher(v_expired)
    assert is_valid is False
    assert "hết" in reason

    # Voucher hợp lệ
    v_good = {
        "voucher_type": "PLATFORM",
        "title": "Giảm 150k cho đơn từ 500k",
        "discount_value": 150000,
        "min_spend": 500000,
        "status": "ACTIVE"
    }
    is_valid, reason = validate_voucher(v_good)
    assert is_valid is True

def test_database_hard_constraint_blocks_freeship():
    """Kiểm tra ràng buộc CHECK (is_freeship = 0) ở mức database"""
    from core.database import get_connection, init_db
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
        INSERT INTO vouchers (
            id, platform_id, voucher_id_on_platform, voucher_type, title,
            discount_type, discount_value, claim_url, is_freeship
        ) VALUES (
            'test_bad_freeship', 'SHOPEE', 'BAD_SHIP_999', 'FREESHIP',
            'Mã Freeship Vi Phạm', 'FIXED_AMOUNT', 30000, 'https://shopee.vn', 1
        )
        """)
        conn.commit()
    conn.close()
