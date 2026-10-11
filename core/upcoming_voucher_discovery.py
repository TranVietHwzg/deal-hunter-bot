from typing import List, Dict, Any, Optional
from models.voucher import Voucher, VoucherStatus, ScopeType
from repositories.voucher_repository import VoucherRepository
from core.voucher_filter import is_freeship, is_worthy_voucher
from core.voucher_verify import verify_hunt_only
from core.voucher_classifier import classify_scope
from core.voucher_lifecycle import determine_initial_status, parse_vietnam_time
from config.settings import settings

class UpcomingVoucherDiscovery:
    def __init__(self, voucher_repo: Optional[VoucherRepository] = None):
        self.voucher_repo = voucher_repo or VoucherRepository()

    def process_collected_vouchers(
        self,
        raw_items: List[Dict[str, Any]],
        min_fixed_discount: Optional[float] = None,
        min_percent_rate: Optional[float] = None,
        min_percent_cap: Optional[float] = None,
        max_lookahead_days: int = 7
    ) -> Dict[str, Any]:
        """
        Xử lý danh sách voucher mới thu thập:
        - Lọc bỏ 100% freeship
        - Lọc theo ngưỡng giá trị đáng báo (Single Source of Truth)
        - Phân loại scope
        - Khởi tạo status ban đầu (UPCOMING_UNKNOWN_CODE, UPCOMING_CODE_KNOWN, ACTIVE...)
        - So sánh với DB và phát hiện biến động (code lộ ra, đổi giờ, đổi mức giảm)
        Trả về kết quả thống kê và danh sách sự kiện cần báo.
        """
        if min_fixed_discount is None:
            min_fixed_discount = getattr(settings, "ELITE_MIN_FIXED_0D", 30000.0)
        if min_percent_rate is None:
            min_percent_rate = getattr(settings, "ELITE_MIN_PERCENT", 30.0)
        if min_percent_cap is None:
            min_percent_cap = getattr(settings, "ELITE_MIN_CAP", 30000.0)
        new_count = 0
        updated_count = 0
        events_to_notify: List[Dict[str, Any]] = []

        for item in raw_items:
            # 1. Zero-freeship filter
            is_ship, reason = is_freeship(item)
            if is_ship:
                continue

            # 1b. Verify hunt-only: chuẩn hóa mã, loại mã rác, không claim
            try:
                ok, _, verified = verify_hunt_only(item)
                if not ok:
                    # vẫn cho sự kiện UPCOMING_UNKNOWN_CODE đi qua nếu thiếu code
                    # còn lại bỏ mã rác / freeship / sai định dạng
                    if not item.get("voucher_code"):
                        verified = item
                    else:
                        continue
                item = verified
            except Exception:
                pass

            # 2. Scope classification
            scope = classify_scope(item)

            # 3. Initial status
            code = item.get("voucher_code")
            # Quy tắc: Không tạo mã giả khi code chưa công bố
            if code and not str(code).strip():
                code = None
            elif code:
                code = str(code).strip().upper()

            start_t = str(item.get("start_time", ""))
            end_t = str(item.get("end_time", ""))
            conf = int(item.get("confidence_score", 90))

            init_status = determine_initial_status(code, start_t, end_t, conf)

            # Đóng gói thành Voucher model
            cat_list = item.get("category_names") or ([item.get("category")] if item.get("category") else [])
            v_model = Voucher(
                id=str(item.get("id") or item.get("voucher_id") or f"SP_{code or 'EVENT'}_{int(item.get('discount_value', 0))}"),
                platform="SHOPEE",
                voucher_code=code,
                title=str(item.get("title", "Shopee Voucher")),
                description=item.get("description"),
                scope_type=scope,
                shop_id=item.get("shop_id"),
                shop_name=item.get("shop_name"),
                shop_url=item.get("shop_url"),
                category_names=cat_list,
                discount_type=item.get("discount_type", "FIXED"),
                discount_value=float(item.get("discount_value", 0)),
                max_discount=float(item.get("max_discount")) if item.get("max_discount") is not None else None,
                min_order_value=float(item.get("min_order_value", 0)),
                start_time=start_t,
                end_time=end_t,
                timezone=item.get("timezone", "Asia/Ho_Chi_Minh"),
                status=init_status,
                is_freeship=0,
                source_url=str(item.get("source_url") or item.get("claim_url") or "https://shopee.vn"),
                source_type=str(item.get("source_type") or "CAMPAIGN_PAGE"),
                confidence_score=conf
            )

            # Kiểm tra ngưỡng đáng báo
            worthy = is_worthy_voucher(
                v_model,
                min_fixed_discount=min_fixed_discount,
                min_percent_rate=min_percent_rate,
                min_percent_cap=min_percent_cap
            )

            # Lưu DB và phát hiện thay đổi
            res = self.voucher_repo.upsert(v_model)
            if res["is_new"]:
                new_count += 1
                if worthy:
                    if v_model.status == VoucherStatus.UPCOMING_CODE_KNOWN:
                        events_to_notify.append({"type": "UPCOMING_KNOWN", "voucher": v_model})
                    elif v_model.status == VoucherStatus.UPCOMING_UNKNOWN_CODE:
                        events_to_notify.append({"type": "UPCOMING_UNKNOWN", "voucher": v_model})
                    elif v_model.status == VoucherStatus.ACTIVE:
                        events_to_notify.append({"type": "ACTIVE_NEW", "voucher": v_model})
            else:
                if res["changes"]:
                    updated_count += 1
                    # Kiểm tra xem có lộ code không
                    code_change = next((c for c in res["changes"] if c["changed_field"] == "voucher_code"), None)
                    time_change = next((c for c in res["changes"] if c["changed_field"] in ("start_time", "end_time")), None)
                    
                    if code_change and worthy:
                        events_to_notify.append({"type": "CODE_REVEALED", "voucher": v_model, "change": code_change})
                    elif time_change and worthy:
                        events_to_notify.append({"type": "TIME_CHANGED", "voucher": v_model, "change": time_change})

        return {
            "new_vouchers": new_count,
            "updated_vouchers": updated_count,
            "events_to_notify": events_to_notify
        }
