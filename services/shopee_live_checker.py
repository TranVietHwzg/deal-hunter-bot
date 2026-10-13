import httpx
import asyncio
import logging
from typing import Dict, Any, Optional, List
from models.voucher import Voucher, VoucherStatus
from repositories.voucher_repository import VoucherRepository

logger = logging.getLogger(__name__)

class ShopeeLiveChecker:
    """
    Dịch vụ Live Status Probe định kỳ kiểm tra trạng thái thực tế của voucher với Shopee API.
    Đặc tính kỹ thuật:
    - 100% Read-only, an toàn tuyệt đối, không spam (delay giữa các request).
    - Endpoint: https://shopee.vn/api/v4/voucher/validate_voucher_code?voucher_code={code}
    - Nếu Shopee xác nhận hết lượt / voucher_status != 1 -> Đánh dấu EXHAUSTED ngay lập tức.
    - Nếu lỗi mạng hoặc rate-limit (403/429) -> Giữ nguyên (an toàn, không hủy nhầm mã).
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://shopee.vn/",
        "Accept": "application/json",
        "x-api-source": "pc"
    }

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout

    async def check_voucher_status(self, voucher: Voucher) -> Dict[str, Any]:
        """
        Kiểm tra trạng thái trực tiếp của 1 voucher với Shopee.
        Trả về dict:
        {
            "voucher_id": str,
            "is_exhausted": Optional[bool],  # True: Hết lượt; False: Còn lượt; None: Không xác định được
            "reason": str,
            "checked_at": str
        }
        """
        code = voucher.voucher_code
        if not code or voucher.claim_type != "CODE":
            # Mã banner không có code ký tự nhập tay
            return {
                "voucher_id": voucher.id,
                "is_exhausted": None,
                "reason": "Voucher banner không có code ký tự để probe API validate",
                "raw_response": None
            }

        url = f"https://shopee.vn/api/v4/voucher/validate_voucher_code?voucher_code={code.strip()}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=self.HEADERS)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        error_code = data.get("error")
                        error_msg = str(data.get("error_msg") or "").lower()
                        
                        # Shopee response: error == 0 nghĩa là voucher hợp lệ
                        if error_code == 0:
                            vdata = data.get("data") or {}
                            vstatus = vdata.get("voucher_status")
                            # voucher_status: 1 = Valid/Claimable, 2 = Fully redeemed/Used up
                            if vstatus == 2:
                                return {
                                    "voucher_id": voucher.id,
                                    "is_exhausted": True,
                                    "reason": "Shopee voucher_status=2 (Đã hết lượt sử dụng)",
                                    "raw_response": data
                                }
                            return {
                                "voucher_id": voucher.id,
                                "is_exhausted": False,
                                "reason": "Shopee xác nhận mã còn lượt",
                                "raw_response": data
                            }
                        else:
                            # Các thông báo lỗi biểu thị voucher hết lượt hoặc vô hiệu
                            exhausted_keywords = [
                                "hết lượt", "fully redeemed", "used up", "không hợp lệ",
                                "không tồn tại", "expired", "quá hạn", "không áp dụng"
                            ]
                            is_exhausted = any(k in error_msg for k in exhausted_keywords) or (error_code in (2, 3, 10001, 10002))
                            return {
                                "voucher_id": voucher.id,
                                "is_exhausted": True if is_exhausted else None,
                                "reason": f"Shopee phản hồi error {error_code}: {data.get('error_msg')}",
                                "raw_response": data
                            }
                    except Exception as json_err:
                        return {
                            "voucher_id": voucher.id,
                            "is_exhausted": None,
                            "reason": f"Phản hồi từ Shopee không phải JSON chuẩn: {json_err}",
                            "raw_response": None
                        }
                elif resp.status_code in (400, 404):
                    return {
                        "voucher_id": voucher.id,
                        "is_exhausted": True,
                        "reason": f"Shopee HTTP {resp.status_code} (Mã không tồn tại hoặc hết hạn)",
                        "raw_response": None
                    }
                else:
                    return {
                        "voucher_id": voucher.id,
                        "is_exhausted": None,
                        "reason": f"Shopee HTTP {resp.status_code} (Rate limit / Chặn bot tạm thời)",
                        "raw_response": None
                    }

        except httpx.TimeoutException:
            return {
                "voucher_id": voucher.id,
                "is_exhausted": None,
                "reason": "Timeout khi kết nối Shopee API",
                "raw_response": None
            }
        except Exception as e:
            return {
                "voucher_id": voucher.id,
                "is_exhausted": None,
                "reason": f"Lỗi kết nối Shopee Live Probe: {e}",
                "raw_response": None
            }

    async def probe_active_vouchers(
        self,
        vouchers: List[Voucher],
        repo: VoucherRepository,
        delay_between_requests: float = 0.5
    ) -> Dict[str, Any]:
        """
        Quét danh sách các voucher đang ACTIVE và tự động cập nhật EXHAUSTED vào DB nếu đã hết lượt.
        """
        checked_count = 0
        exhausted_vouchers: List[Voucher] = []

        for v in vouchers:
            if v.status != VoucherStatus.ACTIVE or not v.voucher_code:
                continue

            checked_count += 1
            res = await self.check_voucher_status(v)
            if res.get("is_exhausted") is True:
                # Cập nhật DB
                v.status = VoucherStatus.EXHAUSTED
                if v.percentage_used is None or v.percentage_used < 100.0:
                    v.percentage_used = 100.0
                repo.update_status(v.id, VoucherStatus.EXHAUSTED)
                with repo.transaction() as cur:
                    cur.execute("UPDATE vouchers SET percentage_used = ? WHERE id = ?", (v.percentage_used, v.id))
                exhausted_vouchers.append(v)
                logger.info(f"[ShopeeLiveChecker] Đã đánh dấu EXHAUSTED cho mã {v.voucher_code} ({v.id}): {res.get('reason')}")

            await asyncio.sleep(delay_between_requests)

        return {
            "total_checked": checked_count,
            "exhausted_count": len(exhausted_vouchers),
            "exhausted_vouchers": exhausted_vouchers
        }
