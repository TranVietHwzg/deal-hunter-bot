from typing import Dict, Any, Optional
from models.voucher import ScopeType, Voucher

def classify_scope(data: Dict[str, Any] or Voucher) -> ScopeType:
    """
    Phân loại phạm vi áp dụng của voucher:
    - SHOP: Áp dụng riêng cho 1 Shop (có shop_id hoặc shop_url hoặc shop_name)
    - CATEGORY: Áp dụng cho ngành hàng hoặc tính năng (Điện Tử, Mẹ & Bé, Shopee Live, Shopee Video)
    - PLATFORM: Áp dụng toàn sàn
    """
    if isinstance(data, Voucher):
        if data.shop_id or data.shop_name or data.shop_url:
            return ScopeType.SHOP
        if data.category_names and len(data.category_names) > 0:
            first_cat = data.category_names[0].lower()
            if "toàn sàn" not in first_cat and "all" not in first_cat:
                return ScopeType.CATEGORY
        return ScopeType.PLATFORM

    shop_id = data.get("shop_id")
    shop_name = data.get("shop_name")
    shop_url = data.get("shop_url")
    vtype = str(data.get("voucher_type", "") or data.get("scope_type", "")).upper()
    cat = str(data.get("category", "") or data.get("category_names", "")).lower()

    if vtype == "SHOP" or shop_id or shop_name or shop_url:
        return ScopeType.SHOP
    
    if vtype in ("CATEGORY", "LIVE_VIDEO") or (cat and "toàn sàn" not in cat and "all" not in cat and "chung" not in cat):
        return ScopeType.CATEGORY

    return ScopeType.PLATFORM
