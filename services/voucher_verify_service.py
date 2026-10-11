"""Wrapper tương thích - logic thật nằm ở core/voucher_verify.py để tránh circular import."""
from core.voucher_verify import normalize_code, verify_hunt_only

__all__ = ["normalize_code", "verify_hunt_only"]
