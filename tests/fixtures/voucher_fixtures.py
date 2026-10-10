from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

def get_test_voucher_fixtures():
    now = datetime.now(VN_TZ)
    today_str = now.strftime("%d/%m/%Y")
    tomorrow_str = (now + timedelta(days=1)).strftime("%d/%m/%Y")
    yesterday_str = (now - timedelta(days=1)).strftime("%d/%m/%Y")

    return [
        # 1. Mã toàn sàn (PLATFORM) - Sắp mở đã biết code
        {
            "id": "FIXTURE_PLATFORM_UPCOMING",
            "voucher_code": "PLATFORM100K",
            "scope_type": "PLATFORM",
            "title": "Mã Toàn Sàn Sắp Mở: Giảm 100k",
            "discount_type": "FIXED",
            "discount_value": 100000,
            "min_order_value": 400000,
            "start_time": f"23:00 {today_str}",
            "end_time": f"23:59 {tomorrow_str}",
            "source_url": "https://shopee.vn/m/sieu-sale",
            "confidence_score": 95,
            "is_freeship": 0
        },
        # 2. Mã ngành hàng (CATEGORY) - Đang active
        {
            "id": "FIXTURE_CATEGORY_ACTIVE",
            "voucher_code": "TECH15PCT",
            "scope_type": "CATEGORY",
            "category": "Điện Tử Công Nghệ",
            "category_names": ["Điện Tử Công Nghệ"],
            "title": "Mã Điện Tử: Giảm 15% tối đa 150k",
            "discount_type": "PERCENT",
            "discount_value": 15,
            "max_discount": 150000,
            "min_order_value": 500000,
            "start_time": f"00:00 {today_str}",
            "end_time": f"23:59 {today_str}",
            "source_url": "https://shopee.vn/m/dien-tu",
            "confidence_score": 90,
            "is_freeship": 0
        },
        # 3. Mã shop riêng (SHOP)
        {
            "id": "FIXTURE_SHOP_VOUCHER",
            "voucher_code": "SHOPAN50K",
            "scope_type": "SHOP",
            "shop_id": "shop_anker_vn",
            "shop_name": "Anker Official",
            "shop_url": "https://shopee.vn/shop_anker_vn",
            "title": "Voucher Shop Anker: Giảm 50k",
            "discount_type": "FIXED",
            "discount_value": 50000,
            "min_order_value": 300000,
            "start_time": f"00:00 {today_str}",
            "end_time": f"23:59 {tomorrow_str}",
            "source_url": "https://shopee.vn/shop_anker_vn",
            "confidence_score": 95,
            "is_freeship": 0
        },
        # 4. Chương trình sắp mở CHƯA có code (UPCOMING_UNKNOWN_CODE)
        {
            "id": "FIXTURE_EVENT_NO_CODE",
            "voucher_code": None,
            "scope_type": "PLATFORM",
            "title": "Siêu Hội Sale Tháng Mới",
            "discount_type": "FIXED",
            "discount_value": 80000,
            "min_order_value": 250000,
            "start_time": f"00:00 {tomorrow_str}",
            "end_time": f"23:59 {tomorrow_str}",
            "source_url": "https://shopee.vn/m/sieu-hoi",
            "confidence_score": 85,
            "is_freeship": 0
        },
        # 5. Mã đã hết hạn (EXPIRED)
        {
            "id": "FIXTURE_EXPIRED_VOUCHER",
            "voucher_code": "OLDVOUCHER50K",
            "scope_type": "PLATFORM",
            "title": "Mã Đã Hết Hạn Hôm Qua",
            "discount_type": "FIXED",
            "discount_value": 50000,
            "min_order_value": 200000,
            "start_time": f"00:00 {yesterday_str}",
            "end_time": f"23:59 {yesterday_str}",
            "source_url": "https://shopee.vn",
            "confidence_score": 90,
            "is_freeship": 0
        },
        # 6. Voucher Freeship (BỊ LOẠI BỎ TRIỆT ĐỂ)
        {
            "id": "FIXTURE_FREESHIP_JUNK",
            "voucher_code": "SHIPFREE0D",
            "scope_type": "PLATFORM",
            "title": "Mã Miễn Phí Vận Chuyển Đơn 0đ",
            "discount_type": "FIXED",
            "discount_value": 30000,
            "min_order_value": 0,
            "start_time": f"00:00 {today_str}",
            "end_time": f"23:59 {today_str}",
            "source_url": "https://shopee.vn/m/mien-phi-van-chuyen",
            "is_freeship": 1
        }
    ]
