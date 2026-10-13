import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship, is_worthy_voucher
from models.voucher import VerificationStatus

VN_TZ = timezone(timedelta(hours=7))

class PersonalEligibleVoucherSource(BaseVoucherSource):
    """Adapter riêng cho nguồn Ví voucher & Giỏ hàng cá nhân.
    Tuân thủ tuyệt đối quy định an toàn:
    - Kích hoạt khi có biến môi trường SHOPEE_COOKIE (read-only) hoặc is_connected=True.
    - Read-only 100%, không auto-claim, không thêm/sửa giỏ hàng, không thanh toán.
    - Dữ liệu cá nhân chỉ dùng để tăng điểm độ tin cậy/khả năng sử dụng (+4đ), KHÔNG hạ tiêu chuẩn Elite (ngưỡng 80đ).
    """

    def __init__(self, is_connected: Optional[bool] = None):
        super().__init__(
            name="personal_eligible_voucher_source",
            source_type="PERSONAL_WALLET_ELIGIBLE",
            rate_limit_per_minute=10,
            failure_threshold=3,
        )
        if is_connected is not None:
            self.is_connected = is_connected
        else:
            self.is_connected = bool(os.environ.get("SHOPEE_COOKIE"))

    def get_status_message(self) -> str:
        if not self.is_connected:
            return (
                "Nguồn Ví voucher cá nhân: Chưa kết nối chính thức.\n"
                "Bot hiện chỉ đánh giá voucher từ nguồn công khai hợp lệ."
            )
        return (
            "Nguồn Ví voucher cá nhân: Đã kết nối chính thức (Read-only).\n"
            "Voucher đủ điều kiện cá nhân được cộng điểm ưu tiên."
        )

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        # Nếu chưa kết nối hợp lệ, trả về rỗng
        if not self.is_connected:
            return []

        cookie = os.environ.get("SHOPEE_COOKIE")
        if not cookie:
            return []

        if not self.circuit_breaker.can_execute():
            return []

        await self.rate_limiter.acquire()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://shopee.vn/user/voucher-wallet",
            "Accept": "application/json",
            "Cookie": cookie,
            "x-api-source": "pc",
            "x-shopee-language": "vi"
        }

        vouchers = []
        now_dt = datetime.now(VN_TZ)
        now_iso = now_dt.isoformat()

        # Endpoints read-only ví voucher của Shopee
        urls = [
            "https://shopee.vn/api/v2/voucher_wallet/get_vouchers?page_type=1",
            "https://shopee.vn/api/v2/voucher_wallet/get_vouchers?page_type=2"
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                for url in urls:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_list = (
                            data.get("data", {}).get("user_vouchers")
                            or data.get("data", {}).get("vouchers")
                            or data.get("vouchers")
                            or []
                        )
                        for item in raw_list:
                            v_info = item.get("voucher") or item
                            code = v_info.get("voucher_code") or v_info.get("code")
                            p_id = str(v_info.get("voucher_id") or v_info.get("promotionid") or "")
                            d_val = float(v_info.get("discount_value") or v_info.get("amount") or v_info.get("discount_percentage") or 0)
                            max_d = float(v_info.get("max_discount") or v_info.get("discount_cap") or d_val)
                            min_sp = float(v_info.get("min_spend") or v_info.get("min_order_value") or 0)
                            is_pct = bool(v_info.get("discount_percentage") or v_info.get("is_percent"))

                            start_ts = v_info.get("start_time")
                            end_ts = v_info.get("end_time")
                            start_str = datetime.fromtimestamp(start_ts, tz=VN_TZ).strftime("%d/%m/%Y %H:%M") if start_ts else now_dt.strftime("%d/%m/%Y 00:00")
                            end_str = datetime.fromtimestamp(end_ts, tz=VN_TZ).strftime("%d/%m/%Y %H:%M") if end_ts else (now_dt + timedelta(days=7)).strftime("%d/%m/%Y 23:59")

                            v_dict = {
                                "id": f"WALLET_{code or p_id}_{int(d_val)}",
                                "voucher_code": code,
                                "claim_type": "CODE" if code else "SAVE_BUTTON",
                                "verification_status": VerificationStatus.VERIFIED_ACTIVE.value,
                                "title": v_info.get("title") or f"Mã trong ví: Giảm {int(d_val)}{'%' if is_pct else 'đ'}",
                                "description": v_info.get("description") or "Voucher sẵn có trong ví Shopee cá nhân",
                                "scope_type": "PLATFORM",
                                "discount_type": "PERCENT" if is_pct else "FIXED",
                                "discount_value": d_val,
                                "max_discount": max_d,
                                "min_order_value": min_sp,
                                "start_time": start_str,
                                "end_time": end_str,
                                "source_url": "https://shopee.vn/user/voucher-wallet",
                                "source_type": "PERSONAL_WALLET_ELIGIBLE",
                                "source_title": "Ví Voucher Shopee Cá Nhân (Read-Only)",
                                "source_captured_at": now_iso,
                                "confidence_score": 95,
                                "is_freeship": 0
                            }

                            ship, _ = is_freeship(v_dict)
                            if not ship and is_worthy_voucher(v_dict):
                                vouchers.append(v_dict)

            self.circuit_breaker.record_success()
        except Exception:
            self.circuit_breaker.record_failure()

        return vouchers
