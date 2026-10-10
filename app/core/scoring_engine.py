from typing import Dict, Any, Tuple
from datetime import datetime, timezone

def calculate_voucher_quality_score(
    voucher_data: Dict[str, Any],
    watchlist_matched: bool = False,
    category_matched: bool = False
) -> Tuple[int, Dict[str, Any]]:
    """
    Tính điểm chất lượng voucher trên thang 0 - 100 theo 7 tiêu chí chuẩn hóa:
    - 30đ: Tiền giảm thực tế
    - 20đ: Tỷ lệ % giảm thực tế
    - 15đ: Mức đơn tối thiểu hợp lý
    - 15đ: Còn lượt & Độ tin cậy dữ liệu
    - 10đ: Khả năng gộp đa tầng
    - 5đ: Phù hợp Watchlist / Ngành hàng
    - 5đ: Khung giờ còn hạn khả thi
    Trừ điểm phạt nếu điều kiện ngặt nghèo hoặc rủi ro.
    
    Trả về: (total_score, breakdown_dict)
    """
    # Nếu là freeship thì trả về 0 điểm ngay lập tức
    from app.core.junk_filter import is_freeship
    is_ship, _ = is_freeship(voucher_data)
    if is_ship:
        return 0, {"reason": "BỊ LOẠI: Freeship tuyệt đối không được chấm điểm", "total": 0}

    discount_type = str(voucher_data.get("discount_type", "FIXED_AMOUNT")).upper()
    discount_val = float(voucher_data.get("discount_value") or voucher_data.get("discount_val") or 0)
    max_discount = float(voucher_data.get("max_discount_amount") or voucher_data.get("max_discount") or (discount_val if discount_type in ["FIXED_AMOUNT", "AMOUNT"] else 100000))
    min_spend = float(voucher_data.get("min_spend") or 0)

    # Tiền giảm thực tế dự kiến
    effective_cash_reduction = max_discount if discount_type in ["PERCENTAGE", "PERCENT"] else discount_val
    # Tỷ lệ % giảm dự kiến
    if discount_type in ["PERCENTAGE", "PERCENT"]:
        effective_percent = discount_val
    else:
        effective_percent = (discount_val / min_spend * 100) if min_spend > 0 else 50.0

    breakdown = {}

    # P1: Số tiền giảm thực tế (Max 30)
    if effective_cash_reduction >= 500000:
        p1 = 30
    elif effective_cash_reduction >= 200000:
        p1 = 25
    elif effective_cash_reduction >= 100000:
        p1 = 20
    elif effective_cash_reduction >= 50000:
        p1 = 15
    elif effective_cash_reduction >= 20000:
        p1 = 8
    else:
        p1 = 3
    breakdown["p1_cash_reduction"] = {"points": p1, "value": f"{int(effective_cash_reduction):,}đ"}

    # P2: Tỷ lệ % giảm thực tế (Max 20)
    if effective_percent >= 50:
        p2 = 20
    elif effective_percent >= 30:
        p2 = 16
    elif effective_percent >= 20:
        p2 = 12
    elif effective_percent >= 15:
        p2 = 8
    else:
        p2 = 2
    breakdown["p2_discount_rate"] = {"points": p2, "value": f"{round(effective_percent, 1)}%"}

    # P3: Mức đơn tối thiểu hợp lý (Max 15)
    if min_spend <= 0:
        p3 = 15
    elif effective_cash_reduction > 0 and (min_spend <= 3 * effective_cash_reduction):
        p3 = 12
    elif effective_cash_reduction > 0 and (min_spend <= 5 * effective_cash_reduction):
        p3 = 8
    elif effective_cash_reduction > 0 and (min_spend <= 8 * effective_cash_reduction):
        p3 = 5
    else:
        p3 = 0
    breakdown["p3_min_spend_ratio"] = {"points": p3, "min_spend": f"{int(min_spend):,}đ"}

    # P4: Còn lượt & Độ tin cậy dữ liệu (Max 15)
    status = str(voucher_data.get("status", "ACTIVE")).upper()
    is_verified = voucher_data.get("is_verified", True)
    if status == "ACTIVE" and is_verified:
        p4 = 15
    elif status == "ACTIVE":
        p4 = 12
    elif status == "UPCOMING":
        p4 = 8
    elif status == "RESTOCKED":
        p4 = 14
    else:
        p4 = 0
    breakdown["p4_availability_confidence"] = {"points": p4, "status": status}

    # P5: Khả năng gộp với voucher shop/sàn khác (Max 10)
    can_stack_shop = voucher_data.get("can_stack_with_shop", True)
    can_stack_plat = voucher_data.get("can_stack_with_platform", False)
    v_type = str(voucher_data.get("voucher_type", "")).upper()
    
    if can_stack_shop and can_stack_plat:
        p5 = 10
    elif can_stack_shop or v_type in ["PLATFORM", "SAN"]:
        p5 = 7
    elif v_type in ["SHOP"]:
        p5 = 6
    else:
        p5 = 2
    breakdown["p5_stackability"] = {"points": p5}

    # P6: Phù hợp Watchlist / Ngành hàng cá nhân (Max 5)
    if watchlist_matched:
        p6 = 5
    elif category_matched:
        p6 = 3
    else:
        p6 = 1
    breakdown["p6_watchlist_relevance"] = {"points": p6}

    # P7: Thời hạn sử dụng khả thi (Max 5)
    p7 = 5
    end_time_raw = voucher_data.get("end_time")
    if end_time_raw:
        try:
            if isinstance(end_time_raw, (int, float)):
                remain_secs = end_time_raw - datetime.now().timestamp()
            elif isinstance(end_time_raw, str):
                dt = datetime.fromisoformat(end_time_raw.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
                remain_secs = (dt - now).total_seconds()
            else:
                remain_secs = 7200
            
            if remain_secs > 7200: # > 2 giờ
                p7 = 5
            elif remain_secs > 900: # 15p - 2 giờ
                p7 = 3
            elif remain_secs > 0:
                p7 = 1
            else:
                p7 = 0
        except Exception:
            p7 = 4
    breakdown["p7_usable_time_window"] = {"points": p7}

    # Các khoản trừ phạt (Penalties)
    penalties = 0
    penalty_reasons = []

    # Phạt tân thủ nếu chưa bật
    if voucher_data.get("is_new_user_only", False):
        penalties += 30
        penalty_reasons.append("Chỉ dành cho khách hàng mới (-30)")

    # Phạt cổng thanh toán độc quyền ngân hàng lạ
    payment_method = str(voucher_data.get("payment_method", "ALL")).upper()
    if payment_method not in ["ALL", "SHOPEEPAY", "COD", "VNPAY", "TIKTOK_PAY", ""]:
        penalties += 15
        penalty_reasons.append(f"Giới hạn thanh toán thẻ {payment_method} (-15)")

    # Phạt đơn tối thiểu quá cao (> 8 lần số tiền giảm)
    if effective_cash_reduction > 0 and min_spend > 8 * effective_cash_reduction and effective_cash_reduction < 500000:
        penalties += 20
        penalty_reasons.append("Đơn tối thiểu quá lớn so với mức giảm (> 8x) (-20)")

    breakdown["penalties"] = {"total_deduction": penalties, "reasons": penalty_reasons}

    raw_sum = p1 + p2 + p3 + p4 + p5 + p6 + p7 - penalties
    total_score = max(0, min(100, raw_sum))
    breakdown["total_score"] = total_score

    return total_score, breakdown
