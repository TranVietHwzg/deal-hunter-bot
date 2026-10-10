# SHOPEE UPCOMING HIDDEN VOUCHER RADAR

Hệ thống Radar Telegram cá nhân chuyên phát hiện và theo dõi **Voucher Shopee Sắp Mở & Mã Ẩn Hợp Lệ**, tập trung vào các mã giảm trực tiếp giá sản phẩm, thời gian hiệu lực chính xác và cảnh báo đúng lúc.

## 1. Tính Năng Cốt Lõi

1. **Phát hiện mã sắp mở:** Theo dõi các voucher/chương trình sắp có hiệu lực trong hôm nay, ngày mai và 7 ngày tới.
2. **Săn mã ẩn công khai:** Thu thập mã giảm giá đã công bố trong chiến dịch, banner, khung giờ vàng hoặc trên trang shop công khai nhưng chưa hiện trong danh sách thông thường.
3. **Phạm vi đa dạng:**
   - **Toàn sàn (PLATFORM)**
   - **Toàn ngành hàng (CATEGORY):** Điện tử, Gia dụng, Shopee Live, Shopee Video
   - **Riêng từng shop (SHOP):** Theo dõi gian hàng theo danh sách cá nhân (`tracked_shops`).
4. **Zero Freeship 100%:** Loại bỏ tuyệt đối mọi mã miễn phí vận chuyển/hỗ trợ phí ship.
5. **State Machine 8 trạng thái:** Quản lý vòng đời chặt chẽ (`DISCOVERED`, `UPCOMING_UNKNOWN_CODE`, `UPCOMING_CODE_KNOWN`, `ACTIVE`, `EXHAUSTED`, `EXPIRED`, `CANCELLED`, `UNVERIFIED`).
6. **Nhắc giờ mở mã:** Tự động gửi cảnh báo trước **15 phút** và **2 phút** khi mã sắp có hiệu lực.
7. **Tần suất thích ứng (Adaptive Polling):** Tự động điều chỉnh khoảng thời gian quét theo khung giờ khuyến mãi, chống spam, tích hợp Circuit Breaker và Exponential Backoff.

## 2. Giao Diện Điều Khiển Telegram (@San_deal_Huvg_bot)

Bàn phím Inline Keyboard 6 nút tối giản:
- `[ 🔍 Quét ngay ]`: Chạy chu kỳ quét toàn diện ngay lập tức.
- `[ 🌐 Mã toàn sàn ]`: Xem mã toàn sàn và toàn ngành (đang active & sắp mở).
- `[ 🏪 Mã từ shop ]`: Xem voucher từ các shop bạn đang theo dõi.
- `[ 📅 Mã sắp mở ]`: Xem danh sách mã & sự kiện sắp mở trong 7 ngày tới.
- `[ ➕ Thêm shop ]`: Dán link shop công khai để thêm vào theo dõi.
- `[ ⚙️ Cài đặt ]`: Xem và tùy chỉnh các ngưỡng cấu hình.

### Lệnh Chat Dự Phòng
- `/scan`: Quét toàn diện ngay lập tức.
- `/upcoming`: Danh sách mã sắp mở 7 ngày tới.
- `/active`: Danh sách mã đang hoạt động.
- `/platform`: Xem mã toàn sàn.
- `/shops`: Xem các shop đang theo dõi.
- `/addshop <link>`: Thêm shop vào danh sách theo dõi.
- `/removeshop <id>`: Xóa shop khỏi danh sách theo dõi.
- `/settings`: Cài đặt hệ thống.
- `/status`: Báo cáo tình trạng Radar.

## 3. Khởi Chạy Hệ Thống

```powershell
py main.py
```

## 4. Chạy Bộ Kiểm Thử (Pytest)

```powershell
py -m pytest tests
```
Tất cả 41/41 unit & integration tests đều vượt qua kiểm tra chất lượng.
