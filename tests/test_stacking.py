import pytest
from app.core.stacking_engine import calculate_stacked_price

def test_four_tier_stacking_calculation():
    """
    Sản phẩm: 1.000.000đ
    - Giảm trực tiếp của shop: 50.000đ -> còn 950.000đ
    - Shop voucher: Giảm 50.000đ -> còn 900.000đ
    - Platform voucher: Giảm 100.000đ -> còn 800.000đ
    - Category/Live voucher: Giảm 50.000đ -> còn 750.000đ
    => Giá thực trả: 750.000đ (Tiết kiệm 250.000đ = 25%)
    """
    shop_voucher = {
        "id": "SHOP_01",
        "title": "Shop Voucher 50k",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 50000,
        "min_spend": 300000,
        "can_stack_with_shop": True
    }
    platform_voucher = {
        "id": "PLAT_01",
        "title": "Voucher Sàn 100k",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 100000,
        "min_spend": 500000,
        "can_stack_with_shop": True
    }
    category_voucher = {
        "id": "CAT_01",
        "title": "Mã Ngành Hàng 50k",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 50000,
        "min_spend": 500000,
        "can_stack_with_shop": True
    }

    res = calculate_stacked_price(
        product_price=1000000,
        shop_direct_discount=50000,
        shop_voucher=shop_voucher,
        platform_voucher=platform_voucher,
        category_live_voucher=category_voucher
    )

    assert res["final_price"] == 750000.0
    assert res["total_savings"] == 250000.0
    assert res["discount_percent"] == 25.0
    assert res["confidence"] == "VERIFIED"
    assert len(res["applied_vouchers"]) == 3

def test_stacking_percentage_and_max_ceiling():
    """
    Sản phẩm: 500.000đ
    - Voucher sàn giảm 20% tối đa 50.000đ (20% của 500k là 100k -> bị chạm trần 50k)
    => Giá sau giảm: 450.000đ
    """
    platform_voucher = {
        "id": "PLAT_PCT",
        "title": "Giảm 20% tối đa 50k",
        "discount_type": "PERCENTAGE",
        "discount_value": 20,
        "max_discount_amount": 50000,
        "min_spend": 200000
    }
    res = calculate_stacked_price(
        product_price=500000,
        platform_voucher=platform_voucher
    )
    assert res["final_price"] == 450000.0
    assert res["applied_breakdown"]["platform_voucher"] == 50000.0

def test_zero_freeship_invariance():
    """Đảm bảo không có trường hay tính toán phí vận chuyển nào tồn tại"""
    res = calculate_stacked_price(product_price=300000)
    assert "shipping_fee" not in res
    assert "freeship" not in res
    assert res["final_price"] == 300000.0
