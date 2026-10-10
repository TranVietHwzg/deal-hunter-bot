import pytest
from app.core.scoring_engine import calculate_voucher_quality_score

def test_hot_voucher_score_gte_85():
    # Siêu voucher: Giảm 200k đơn từ 600k (Min spend = 3x discount), còn lượt, toàn sàn
    v_hot = {
        "voucher_type": "PLATFORM",
        "title": "Giảm 200k đơn từ 600k",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 200000,
        "max_discount_amount": 200000,
        "min_spend": 600000,
        "status": "ACTIVE",
        "is_verified": True,
        "can_stack_with_shop": True,
        "can_stack_with_platform": True
    }
    score, breakdown = calculate_voucher_quality_score(v_hot, watchlist_matched=True)
    assert score >= 85, f"Expected HOT score >= 85, got {score}. Breakdown: {breakdown}"

def test_low_value_voucher_score_lt_70():
    # Voucher bèo: Giảm 10k đơn từ 300k (Min spend = 30x discount)
    v_low = {
        "voucher_type": "SHOP",
        "title": "Giảm 10k đơn 300k",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 10000,
        "max_discount_amount": 10000,
        "min_spend": 300000,
        "status": "ACTIVE"
    }
    score, breakdown = calculate_voucher_quality_score(v_low)
    assert score < 70, f"Expected score < 70 for low tier, got {score}"

def test_penalties_applied():
    # Voucher có đơn tối thiểu gấp 10 lần tiền giảm (MinSpend > 8x MaxDiscount)
    v_penalized = {
        "voucher_type": "SHOP",
        "title": "Giảm 50k đơn từ 1.000.000đ",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 50000,
        "max_discount_amount": 50000,
        "min_spend": 1000000,
        "is_new_user_only": True, # Bị phạt -30
        "payment_method": "VPBANK_CREDIT" # Bị phạt -15
    }
    score, breakdown = calculate_voucher_quality_score(v_penalized)
    assert breakdown["penalties"]["total_deduction"] >= 45
    assert score < 50

def test_freeship_always_returns_zero():
    v_ship = {
        "voucher_type": "FREESHIP",
        "title": "Miễn phí vận chuyển 50k",
        "discount_value": 50000,
        "min_spend": 0
    }
    score, breakdown = calculate_voucher_quality_score(v_ship)
    assert score == 0
