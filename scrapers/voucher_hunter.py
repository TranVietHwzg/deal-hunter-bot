"""
Module Săn & Tổng Hợp Voucher Shopee Toàn Diện (Voucher Hunter Engine)
Phân loại đầy đủ: Video, Live, Khung giờ toàn sàn, Freeship Xtra, Hoàn Xu, Điện tử
Kèm Link nhận trực tiếp và Hướng dẫn sử dụng từng loại mã.
"""

def get_comprehensive_voucher_catalog():
    """
    Kho voucher Shopee chuyên sâu, phân loại rõ ràng, có link nhận và hướng dẫn chi tiết
    """
    return [
        # --- 1. VOUCHER SHOPEE VIDEO (GIẢM SÂU NHẤT 20% - 50%) ---
        {
            "voucher_id": "SP_VIDEO_50PCT",
            "voucher_code": "LƯU TRÊN VIDEO",
            "voucher_type": "VIDEO",
            "category": "Shopee Video",
            "discount_type": "PERCENT",
            "discount_val": 50,
            "max_discount": 40000,
            "min_spend": 80000,
            "label": "Giảm 50% tối đa 40k (Đơn từ 80k)",
            "claim_url": "https://shopee.vn/m/voucher-video",
            "guide": "1. Bấm link nhận mã hoặc mở mục 'Live & Video' trên Shopee.\n2. Tìm video có sản phẩm bạn muốn mua.\n3. Bấm vào giỏ hàng màu vàng ở góc dưới video rồi áp mã thanh toán.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_VIDEO_20PCT_MAX100K",
            "voucher_code": "LƯU TRÊN VIDEO",
            "voucher_type": "VIDEO",
            "category": "Shopee Video",
            "discount_type": "PERCENT",
            "discount_val": 20,
            "max_discount": 100000,
            "min_spend": 200000,
            "label": "Giảm 20% tối đa 100k (Đơn từ 200k)",
            "claim_url": "https://shopee.vn/m/voucher-video",
            "guide": "Áp dụng cho mọi sản phẩm được thêm vào giỏ từ Shopee Video. Giảm tối đa 100.000đ cho đơn từ 200.000đ.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_VIDEO_25PCT_MAX150K",
            "voucher_code": "LƯU TRÊN VIDEO",
            "voucher_type": "VIDEO",
            "category": "Shopee Video",
            "discount_type": "PERCENT",
            "discount_val": 25,
            "max_discount": 150000,
            "min_spend": 300000,
            "label": "Giảm 25% tối đa 150k (Đơn từ 300k)",
            "claim_url": "https://shopee.vn/m/voucher-video",
            "guide": "Mã VIP Shopee Video, mở mới vào 0h mỗi ngày. Dành cho đơn hàng giá trị từ 300k trở lên.",
            "is_high_tier": 1,
            "is_active": 1
        },

        # --- 2. VOUCHER SHOPEE LIVE (LIVESTREAM) ---
        {
            "voucher_id": "SP_LIVE_15PCT_MAX70K",
            "voucher_code": "LƯU TRÊN LIVE",
            "voucher_type": "LIVE",
            "category": "Shopee Live",
            "discount_type": "PERCENT",
            "discount_val": 15,
            "max_discount": 70000,
            "min_spend": 150000,
            "label": "Giảm 15% tối đa 70k (Đơn từ 150k)",
            "claim_url": "https://shopee.vn/m/shopeelive",
            "guide": "1. Mở link xem Livestream bất kỳ của shop hoặc KOL.\n2. Nhấn vào túi hàng màu cam trong live, tìm mã và bấm 'Lưu'.\n3. Khi thanh toán chọn mã giảm giá Live.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_LIVE_20PCT_MAX100K",
            "voucher_code": "LƯU TRÊN LIVE",
            "voucher_type": "LIVE",
            "category": "Shopee Live",
            "discount_type": "PERCENT",
            "discount_val": 20,
            "max_discount": 100000,
            "min_spend": 250000,
            "label": "Giảm 20% tối đa 100k (Đơn từ 250k - Thời Trang & Mỹ Phẩm)",
            "claim_url": "https://shopee.vn/m/shopeelive",
            "guide": "Chuyên dùng cho ngành hàng Thời trang, Phụ kiện, Mỹ phẩm khi mua qua livestream của shop.",
            "is_high_tier": 1,
            "is_active": 1
        },

        # --- 3. VOUCHER KHUNG GIỜ VÀNG TOÀN SÀN (0H - 9H - 12H - 21H) ---
        {
            "voucher_id": "SP_GLOBAL_15PCT_MAX150K",
            "voucher_code": "TOÀN SÀN 15%",
            "voucher_type": "PLATFORM",
            "category": "Mã Toàn Sàn",
            "discount_type": "PERCENT",
            "discount_val": 15,
            "max_discount": 150000,
            "min_spend": 400000,
            "label": "Giảm 15% tối đa 150k (Đơn từ 400k)",
            "claim_url": "https://shopee.vn/m/ma-giam-gia",
            "guide": "Mã mở bán vào 0h, 9h, 12h, 21h hàng ngày tại 'Trạm Voucher'. Cần vào bấm lưu trước giờ G 5 phút để có trong ví.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_GLOBAL_50K_DON0D",
            "voucher_code": "GIẢM 50K ĐƠN 0Đ",
            "voucher_type": "PLATFORM",
            "category": "Mã Toàn Sàn",
            "discount_type": "FIXED",
            "discount_val": 50000,
            "max_discount": 50000,
            "min_spend": 0,
            "label": "Giảm 50.000đ cho đơn từ 0đ (Khung 0h/12h)",
            "claim_url": "https://shopee.vn/m/khung-gio-san-sale",
            "guide": "Deal 0đ đỉnh nhất! Áp dụng đơn từ 0đ, mở lúc 0h và 12h. Hết sau 3 giây, nên canh bấm lưu và áp ngay lập tức.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_GLOBAL_10PCT_MAX500K",
            "voucher_code": "MALL 10% MAX 500K",
            "voucher_type": "PLATFORM",
            "category": "Mã Toàn Sàn",
            "discount_type": "PERCENT",
            "discount_val": 10,
            "max_discount": 500000,
            "min_spend": 1500000,
            "label": "Giảm 10% tối đa 500k (Đơn từ 1.5 triệu)",
            "claim_url": "https://shopee.vn/m/ma-giam-gia",
            "guide": "Chuyên dùng cho hàng điện máy, đồ gia dụng, laptop, điện thoại. Giảm thẳng nửa triệu khi thanh toán.",
            "is_high_tier": 1,
            "is_active": 1
        },

        # --- 4. VOUCHER MIỄN PHÍ VẬN CHUYỂN (FREESHIP XTRA) ---
        {
            "voucher_id": "SP_FREESHIP_0D",
            "voucher_code": "FREESHIP 0Đ",
            "voucher_type": "FREESHIP",
            "category": "Freeship",
            "discount_type": "FIXED",
            "discount_val": 15000,
            "max_discount": 15000,
            "min_spend": 0,
            "label": "Freeship Đơn 0đ: Hỗ trợ 15.000đ phí ship",
            "claim_url": "https://shopee.vn/m/mien-phi-van-chuyen",
            "guide": "Giúp gom đơn 1k/0đ mà không tốn tiền ship. Tự động có sẵn trong ví voucher vào đầu mỗi tuần hoặc ngày đôi.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_FREESHIP_XTRA_70K",
            "voucher_code": "FREESHIP XTRA 70K",
            "voucher_type": "FREESHIP",
            "category": "Freeship",
            "discount_type": "FIXED",
            "discount_val": 70000,
            "max_discount": 70000,
            "min_spend": 300000,
            "label": "Freeship Xtra: Hỗ trợ tới 70.000đ (Đơn từ 300k)",
            "claim_url": "https://shopee.vn/m/mien-phi-van-chuyen",
            "guide": "Áp dụng cho các shop có logo 'Freeship Xtra'. Giảm tối đa 70k tiền ship cho các đơn hàng cồng kềnh hoặc giao xa.",
            "is_high_tier": 1,
            "is_active": 1
        },

        # --- 5. VOUCHER ĐIỆN TỬ & CÔNG NGHỆ (TECH ZONE) ---
        {
            "voucher_id": "SP_TECH_7PCT_MAX1TR",
            "voucher_code": "TECH7MAX1TR",
            "voucher_type": "CATEGORY",
            "category": "Điện Tử - Công Nghệ",
            "discount_type": "PERCENT",
            "discount_val": 7,
            "max_discount": 1000000,
            "min_spend": 3000000,
            "label": "Điện Tử: Giảm 7% tối đa 1.000.000đ (Đơn từ 3 triệu)",
            "claim_url": "https://shopee.vn/m/dien-tu-cong-nghe",
            "guide": "Dành riêng cho PC, Laptop, Màn hình, Tai nghe, Điện thoại. Vào trang 'Điện Tử Công Nghệ' để bấm lưu.",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SP_TECH_10PCT_MAX300K",
            "voucher_code": "TECH10MAX300K",
            "voucher_type": "CATEGORY",
            "category": "Điện Tử - Công Nghệ",
            "discount_type": "PERCENT",
            "discount_val": 10,
            "max_discount": 300000,
            "min_spend": 1000000,
            "label": "Điện Tử: Giảm 10% tối đa 300k (Đơn từ 1 triệu)",
            "claim_url": "https://shopee.vn/m/dien-tu-cong-nghe",
            "guide": "Áp dụng mua chuột máy tính, bàn phím cơ, sạc dự phòng, củ sạc nhanh của các shop chính hãng Mall.",
            "is_high_tier": 1,
            "is_active": 1
        },

        # --- 6. VOUCHER HOÀN XU XTRA (CASHBACK) ---
        {
            "voucher_id": "SP_COIN_15PCT_MAX100K",
            "voucher_code": "HOÀN 15% XU",
            "voucher_type": "CASHBACK",
            "category": "Hoàn Xu Xtra",
            "discount_type": "PERCENT",
            "discount_val": 15,
            "max_discount": 100000,
            "min_spend": 200000,
            "label": "Hoàn 15% Xu tối đa 100.000 xu (Đơn từ 200k)",
            "claim_url": "https://shopee.vn/m/hoan-xu-xtra",
            "guide": "Áp dụng cho shop có logo 'Hoàn Xu Xtra'. Xu nhận lại dùng để trừ tiền thẳng vào đơn mua hàng lần kế tiếp (1 xu = 1 VNĐ).",
            "is_high_tier": 1,
            "is_active": 1
        }
    ]
