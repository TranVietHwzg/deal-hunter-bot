"""
Module Săn & Tổng Hợp Voucher Shopee Toàn Diện (Voucher Hunter Engine)
CHUẨN PRODUCTION: BÀI TRỪ FREESHIP 100% - KHÔNG ẢO 0Đ - TẬP TRUNG GIẢM TRỰC TIẾP GIÁ SẢN PHẨM
"""

def get_comprehensive_voucher_catalog():
    """
    Kho voucher Shopee chuyên sâu, phân loại rõ ràng, có link nhận và hướng dẫn chi tiết.
    TUYỆT ĐỐI KHÔNG CHỨA FREESHIP HOẶC HỨA HẸN 0Đ ẢO.
    """
    return [
        # --- 1. VOUCHER SHOPEE VIDEO (GIẢM SÂU 20% - 50%) ---
        {
            "voucher_id": "SP_VIDEO_20PCT_MAX100K",
            "voucher_code": "LƯU TRÊN VIDEO",
            "voucher_type": "LIVE_VIDEO",
            "category": "Shopee Video",
            "title": "Shopee Video: Giảm 20% tối đa 100k đơn từ 200k",
            "discount_type": "PERCENTAGE",
            "discount_value": 20,
            "max_discount_amount": 100000,
            "min_spend": 200000,
            "claim_url": "https://shopee.vn/universal-link/video",
            "guide": "1. Mở App Shopee -> Tab Video.\n2. Tìm sản phẩm bạn muốn mua trên video.\n3. Nhấn vào giỏ hàng màu vàng ở góc dưới video rồi bấm đặt mua để áp mã.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },
        {
            "voucher_id": "SP_VIDEO_25PCT_MAX150K",
            "voucher_code": "LƯU TRÊN VIDEO",
            "voucher_type": "LIVE_VIDEO",
            "category": "Shopee Video",
            "title": "Shopee Video: Giảm 25% tối đa 150k đơn từ 300k",
            "discount_type": "PERCENTAGE",
            "discount_value": 25,
            "max_discount_amount": 150000,
            "min_spend": 300000,
            "claim_url": "https://shopee.vn/universal-link/video",
            "guide": "Mã VIP Shopee Video mở vào các khung giờ chính. Dành cho đơn hàng giá trị từ 300k trở lên.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },

        # --- 2. VOUCHER SHOPEE LIVE (LIVESTREAM) ---
        {
            "voucher_id": "SP_LIVE_15PCT_MAX70K",
            "voucher_code": "LƯU TRÊN LIVE",
            "voucher_type": "LIVE_VIDEO",
            "category": "Shopee Live",
            "title": "Shopee Live: Giảm 15% tối đa 70k đơn từ 150k",
            "discount_type": "PERCENTAGE",
            "discount_value": 15,
            "max_discount_amount": 70000,
            "min_spend": 150000,
            "claim_url": "https://shopee.vn/universal-link/live",
            "guide": "1. Mở xem Livestream của shop hoặc mời gắn tag Live.\n2. Nhấn túi hàng cam trong live, tìm mã bấm 'Lưu'.\n3. Đặt mua trong giỏ live để áp mã.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },
        {
            "voucher_id": "SP_LIVE_20PCT_MAX100K",
            "voucher_code": "LƯU TRÊN LIVE",
            "voucher_type": "LIVE_VIDEO",
            "category": "Shopee Live",
            "title": "Shopee Live: Giảm 20% tối đa 100k đơn từ 250k",
            "discount_type": "PERCENTAGE",
            "discount_value": 20,
            "max_discount_amount": 100000,
            "min_spend": 250000,
            "claim_url": "https://shopee.vn/universal-link/live",
            "guide": "Chuyên dùng cho ngành Thời trang, Phụ kiện, Mỹ phẩm khi mua qua livestream của shop.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },

        # --- 3. VOUCHER KHUNG GIỜ TOÀN SÀN (GIẢM LỚN TIỀN MẶT) ---
        {
            "voucher_id": "SP_GLOBAL_15PCT_MAX150K",
            "voucher_code": "TOÀN SÀN 15%",
            "voucher_type": "PLATFORM",
            "category": "Mã Toàn Sàn",
            "title": "Toàn Sàn: Giảm 15% tối đa 150k đơn từ 400k",
            "discount_type": "PERCENTAGE",
            "discount_value": 15,
            "max_discount_amount": 150000,
            "min_spend": 400000,
            "claim_url": "https://shopee.vn/m/ma-giam-gia",
            "guide": "Lưu tại banner Trạm Voucher trên trang chủ Shopee vào 0h, 9h, 12h, 21h.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },
        {
            "voucher_id": "SP_GLOBAL_10PCT_MAX500K",
            "voucher_code": "MALL 10% MAX 500K",
            "voucher_type": "PLATFORM",
            "category": "Mã Toàn Sàn",
            "title": "Toàn Sàn Shopee Mall: Giảm 10% tối đa 500k đơn từ 1.5 triệu",
            "discount_type": "PERCENTAGE",
            "discount_value": 10,
            "max_discount_amount": 500000,
            "min_spend": 1500000,
            "claim_url": "https://shopee.vn/m/ma-giam-gia",
            "guide": "Chuyên dùng cho hàng điện máy, đồ gia dụng, laptop, điện thoại. Giảm thẳng nửa triệu khi thanh toán.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },
        {
            "voucher_id": "SP_GLOBAL_200K_DON600K",
            "voucher_code": "SALE200K",
            "voucher_type": "PLATFORM",
            "category": "Siêu Sale Sàn",
            "title": "Siêu Sale: Giảm 200.000đ trực tiếp đơn từ 600k",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 200000,
            "max_discount_amount": 200000,
            "min_spend": 600000,
            "claim_url": "https://shopee.vn/m/ma-giam-gia",
            "guide": "Vào Trạm Voucher bấm lưu mã trước giờ sale 5 phút để có trong ví.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },

        # --- 4. VOUCHER NGÀNH HÀNG ĐIỆN TỬ & CÔNG NGHỆ (TECH ZONE) ---
        {
            "voucher_id": "SP_TECH_7PCT_MAX1TR",
            "voucher_code": "TECH7MAX1TR",
            "voucher_type": "CATEGORY",
            "category": "Điện Tử - Công Nghệ",
            "title": "Điện Tử Công Nghệ: Giảm 7% tối đa 1.000.000đ đơn từ 3 triệu",
            "discount_type": "PERCENTAGE",
            "discount_value": 7,
            "max_discount_amount": 1000000,
            "min_spend": 3000000,
            "claim_url": "https://shopee.vn/m/dien-tu-cong-nghe",
            "guide": "Dành riêng cho PC, Laptop, Màn hình, Tai nghe, Điện thoại. Vào trang 'Điện Tử Công Nghệ' để bấm lưu.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },
        {
            "voucher_id": "SP_TECH_10PCT_MAX300K",
            "voucher_code": "TECH10MAX300K",
            "voucher_type": "CATEGORY",
            "category": "Điện Tử - Công Nghệ",
            "title": "Điện Tử: Giảm 10% tối đa 300k đơn từ 1 triệu",
            "discount_type": "PERCENTAGE",
            "discount_value": 10,
            "max_discount_amount": 300000,
            "min_spend": 1000000,
            "claim_url": "https://shopee.vn/m/dien-tu-cong-nghe",
            "guide": "Áp dụng mua chuột máy tính, bàn phím cơ, sạc dự phòng, củ sạc nhanh của các shop Mall.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },

        # --- 5. VOUCHER SHOP GIAN HÀNG CHÍNH HÃNG (SHOP VOUCHERS) ---
        {
            "voucher_id": "SP_SHOP_DAREU_50K",
            "voucher_code": "DAREU50K",
            "voucher_type": "SHOP",
            "category": "Voucher Shop",
            "title": "Gian Hàng Dareu: Giảm 50.000đ cho đơn từ 300k",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 50000,
            "max_discount_amount": 50000,
            "min_spend": 300000,
            "shop_id": "88888",
            "shop_name": "DareU Official Store",
            "claim_url": "https://shopee.vn/mall",
            "guide": "Lưu trực tiếp tại trang chủ gian hàng DareU trên Shopee Mall.",
            "is_freeship": 0,
            "status": "ACTIVE"
        },
        {
            "voucher_id": "SP_SHOP_SOUNDPEATS_80K",
            "voucher_code": "SOUNDPEATS80K",
            "voucher_type": "SHOP",
            "category": "Voucher Shop",
            "title": "Gian Hàng Soundpeats: Giảm 80.000đ cho đơn từ 450k",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 80000,
            "max_discount_amount": 80000,
            "min_spend": 450000,
            "shop_id": "99999",
            "shop_name": "Soundpeats Official",
            "claim_url": "https://shopee.vn/mall",
            "guide": "Lưu trực tiếp tại trang chủ gian hàng Soundpeats trên Shopee Mall.",
            "is_freeship": 0,
            "status": "ACTIVE"
        }
    ]
