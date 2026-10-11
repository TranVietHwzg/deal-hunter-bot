# ELITE SHOPEE VOUCHER RADAR

Hệ thống Radar Telegram cá nhân chuyên phát hiện và chọn lọc **Voucher Shopee Thật Sự Đáng Săn (Chuẩn Elite)**, loại bỏ triệt để các mã phổ thông, mã yếu hoặc mã điều kiện đơn quá cao.

---

## 1. Triết Lý & Cổng Lọc Cứng (Elite Filter)

Bot không gửi tin chỉ vì mã "mới" hay "sắp mở". Chỉ những voucher đạt các tiêu chuẩn tiết kiệm thực tế mới được lưu và thông báo:

1. **Mã giảm tiền cố định:**
   - Giảm từ **30.000đ** trở lên với **đơn tối thiểu 0đ**; HOẶC
   - Giảm từ **50.000đ** trở lên với tỷ lệ đơn tối thiểu: `min_order_value / discount_value <= 3.0` (Ví dụ: Giảm 50k đơn 150k, Giảm 100k đơn 300k).
2. **Mã giảm phần trăm:**
   - Giảm từ **30%** trở lên.
   - Mức giảm tối đa (trần giảm) từ **50.000đ** trở lên.
   - Tiết kiệm ước tính tại đơn tối thiểu: `min(min_order * discount_percent, max_discount) >= 30.000đ`.
   - Điều kiện đơn không được quá 4 lần trần giảm (loại bỏ các mã giảm 30% tối đa 100k nhưng đơn bắt từ 2 triệu).
3. **Tuyệt đối KHÔNG Freeship (100% Loại bỏ):** Không freeship, không hỗ trợ ship, không trợ giá vận chuyển.
4. **Không theo dõi giá sản phẩm:** Vô hiệu hóa hoàn toàn watchlist, price watcher, price stacker.

---

## 2. Thang Điểm Elite Voucher Score (0–100)

Mỗi voucher sau khi qua cổng lọc cứng được chấm điểm theo 6 tiêu chí:
* **Giá trị giảm thực tế (tối đa 30đ):** 30k–49k (10đ), 50k–99k (18đ), 100k–199k (25đ), >=200k (30đ).
* **Tỷ lệ giảm (tối đa 20đ):** 30%–39% (10đ), 40%–49% (15đ), >=50% (20đ). Fixed: tính theo `discount / min_order` (đơn 0đ: 20đ).
* **Điều kiện đơn tối thiểu (tối đa 20đ):** Đơn 0đ (20đ), đơn <= 2 lần giảm (16đ), <= 3 lần (12đ), <= 4 lần (5đ), > 4 lần (0đ).
* **Phạm vi áp dụng (tối đa 10đ):** Toàn sàn (10đ), Ngành hàng rộng (7đ), Shop trong danh sách theo dõi (8đ), Shop không theo dõi (3đ).
* **Độ tin cậy & khả năng dùng (tối đa 15đ):** Nguồn chính thức xác minh (5đ), Còn lượt/chưa hết hạn (3đ), Thời gian rõ ràng (3đ), Đã xác nhận đủ điều kiện tài khoản (4đ).
* **Tính khẩn cấp (tối đa 5đ):** Sắp mở trong 24h (3đ), Còn hiệu lực dưới 2h (5đ).

### Phân Loại Cảnh Báo
| Điểm | Nhãn | Hành động |
|---:|---|---|
| **90–100** | 🔥 **SIÊU XỊN** | Báo ngay, nhắc trước 15 phút và 2 phút trước khi mở |
| **80–89** | ✅ **ĐÁNG LẤY** | Báo 1 lần khi phát hiện |
| **Dưới 80** | Không đủ chuẩn | **Tuyệt đối KHÔNG gửi Telegram** |

---

## 3. Giao Diện Telegram 5 Nút Chuẩn (@San_deal_Huvg_bot)

```text
[ 🔥 Mã siêu xịn ]
[ 📅 Sắp mở    ] [ 🏪 Mã shop   ]
[ 🔍 Quét ngay ] [ ⚙️ Cài đặt   ]
```

* **`🔥 Mã siêu xịn`**: Xem danh sách mã đạt điểm >= 80 (nhóm 90–100 và 80–89).
* **`📅 Sắp mở`**: Xem các mã Elite sắp mở trong 7 ngày tới (sắp xếp: thời gian gần nhất ➔ điểm cao hơn ➔ mức giảm lớn hơn).
* **`🏪 Mã shop`**: Chỉ hiển thị voucher đạt chuẩn Elite của các gian hàng bạn đang theo dõi.
* **`🔍 Quét ngay`**: Chạy chu kỳ quét toàn diện các nguồn và trả về bảng tổng kết minh bạch (Nguồn đã quét, Voucher phát hiện, Voucher bị loại, Voucher Elite mới/cập nhật/sắp mở).
* **`⚙️ Cài đặt`**: Cấu hình các ngưỡng lọc cá nhân (không có tùy chọn Freeship).

---

## 4. Nguồn Ví Voucher Cá Nhân (`personal_eligible_voucher_source`)

* **Chính sách an toàn:** Tuân thủ 100% nguyên tắc Read-Only, không lưu cookie thô, không private endpoint, không lưu/claim mã hộ, không đụng vào giỏ hàng hay thanh toán.
* **Minh bạch:** Khi chưa có kết nối chính thức được phê duyệt, hệ thống hiển thị rõ ràng trong `/status`:
  > *"Nguồn Ví voucher cá nhân: Chưa kết nối chính thức. Bot hiện chỉ đánh giá voucher từ nguồn công khai hợp lệ."*
* **Điểm thưởng:** Dữ liệu cá nhân chỉ dùng để cộng thêm 4 điểm tin cậy/khả năng sử dụng, tuyệt đối không dùng để hạ ngưỡng chuẩn Elite (80 điểm).

---

## 5. Chạy Kiểm Thử Toàn Diện (Pytest)

```powershell
py -m pytest tests
```
Tất cả **59/59 unit & integration tests** đều vượt qua kiểm tra chất lượng (100% PASS), bao gồm 18 kịch bản kiểm thử bắt buộc cho bộ lọc Elite.
