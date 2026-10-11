from typing import Dict, Any, Optional
from models.voucher import Voucher

class VoucherEligibilityChecker:
    """Kiểm tra tính tương thích và điều kiện áp dụng voucher cho tài khoản cá nhân.
    Tuân thủ nguyên tắc read-only, không yêu cầu session/cookie trái phép.
    """
    def __init__(self, is_connected: bool = False):
        self.is_connected = is_connected

    def check_personal_eligibility(self, voucher: Dict[str, Any] or Voucher) -> bool:
        """Nếu có tích hợp chính thức và tài khoản đủ điều kiện thì trả về True, ngược lại False."""
        if not self.is_connected:
            return False
        # Nếu có tích hợp chính thức trong tương lai, kiểm tra thuộc tính ví tại đây
        return False

    def is_new_user_exclusive(self, voucher: Dict[str, Any] or Voucher) -> bool:
        from core.elite_voucher_filter import is_new_user_voucher
        return is_new_user_voucher(voucher)
