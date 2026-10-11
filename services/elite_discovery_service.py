import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from models.scan_run import ScanMode
from models.voucher import Voucher, VoucherStatus, ScopeType, VerificationStatus
from repositories.scan_repository import ScanRepository
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from core.elite_voucher_filter import is_elite_voucher
from core.elite_score_calculator import calculate_elite_score
from core.voucher_lifecycle import determine_initial_status
from core.voucher_classifier import classify_scope
from sources.shopee_platform_campaigns import ShopeePlatformCampaignSource
from sources.shopee_shop_campaigns import ShopeeShopCampaignSource
from sources.personal_eligible_voucher_source import PersonalEligibleVoucherSource
from sources.community_voucher_source import CommunityVoucherSource
from sources.payment_voucher_source import PaymentVoucherSource
from sources.live_video_voucher_source import LiveVideoVoucherSource
from sources.public_banner_source import PublicBannerSource
from sources.leak_inbox_source import LeakInboxSource

class EliteDiscoveryService:
    """Dịch vụ quét và phát hiện Elite Shopee Voucher:
    - Áp dụng bộ lọc cứng is_elite_voucher
    - Chấm điểm chuẩn 0-100 qua calculate_elite_score
    - Chỉ cho phép voucher đạt điểm >= 80 vào danh sách thông báo
    """
    def __init__(
        self,
        voucher_repo: Optional[VoucherRepository] = None,
        scan_repo: Optional[ScanRepository] = None,
        shop_repo: Optional[ShopRepository] = None
    ):
        self.voucher_repo = voucher_repo or VoucherRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.shop_repo = shop_repo or ShopRepository()

        self.platform_source = ShopeePlatformCampaignSource()
        self.shop_source = ShopeeShopCampaignSource()
        self.personal_source = PersonalEligibleVoucherSource(is_connected=False)
        self.community_source = CommunityVoucherSource()
        self.payment_source = PaymentVoucherSource()
        self.live_video_source = LiveVideoVoucherSource()
        self.banner_source = PublicBannerSource()
        self.leak_source = LeakInboxSource()

    async def run_elite_scan(
        self,
        scan_mode: ScanMode = ScanMode.AUTO,
        min_elite_score: int = 80
    ) -> Dict[str, Any]:
        scan_id = f"SCAN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.scan_repo.start_scan_run(scan_id, scan_mode, "elite_radar_sources")

        collected_items: List[Dict[str, Any]] = []
        errors = []
        sources_scanned = 0

        # Danh sách shop được theo dõi
        tracked_shop_ids = set()
        try:
            for s in self.shop_repo.get_tracked_shops(enabled_only=True):
                tracked_shop_ids.add(str(s.shop_id).lower())
                if s.shop_name:
                    tracked_shop_ids.add(str(s.shop_name).lower())
        except Exception:
            pass

        # 1. Platform & Category
        try:
            collected_items.extend(await self.platform_source.fetch_vouchers())
            sources_scanned += 1
        except Exception as e:
            errors.append(f"Platform: {e}")

        # 2. Tracked Shops
        try:
            collected_items.extend(await self.shop_source.fetch_vouchers())
            sources_scanned += 1
        except Exception as e:
            errors.append(f"Shop: {e}")

        # 3. Personal wallet (read-only)
        try:
            collected_items.extend(await self.personal_source.fetch_vouchers())
            sources_scanned += 1
        except Exception as e:
            errors.append(f"Personal: {e}")

        # 4. Banner public
        try:
            collected_items.extend(await self.banner_source.fetch_vouchers())
            sources_scanned += 1
        except Exception as e:
            errors.append(f"Banner: {e}")

        # 5. Community & Partners
        try:
            collected_items.extend(await self.community_source.fetch_vouchers())
            collected_items.extend(await self.payment_source.fetch_vouchers())
            collected_items.extend(await self.live_video_source.fetch_vouchers())
            collected_items.extend(await self.leak_source.fetch_vouchers())
        except Exception as e:
            errors.append(f"Community/Partners: {e}")

        # Lọc và chấm điểm Elite
        items_scanned = len(collected_items)
        items_rejected = 0
        elite_new = 0
        elite_updated = 0
        elite_upcoming = 0
        events_to_notify: List[Dict[str, Any]] = []

        for item in collected_items:
            # 1. Xác định verification_status của item
            raw_vs = item.get("verification_status") or "UNVERIFIED"
            try:
                ver_status = VerificationStatus(raw_vs)
            except Exception:
                ver_status = VerificationStatus.UNVERIFIED

            # 2. Cổng lọc cứng Elite (Yêu cầu đầy đủ bằng chứng)
            is_elite, reason = is_elite_voucher(item, require_evidence=True)

            code = item.get("voucher_code")
            code = str(code).strip().upper() if code and str(code).strip() else None
            start_t = str(item.get("start_time", ""))
            end_t = str(item.get("end_time", ""))
            scope = classify_scope(item)
            cat_list = item.get("category_names") or ([item.get("category")] if item.get("category") else [])

            # Nếu không đạt Elite:
            if not is_elite:
                items_rejected += 1
                # Vẫn lưu vào database nếu không phải freeship để phục vụ audit / unverified
                if not item.get("is_freeship"):
                    rej_model = Voucher(
                        id=str(item.get("id") or item.get("voucher_id") or f"REJ_{code or 'NOCODE'}_{int(item.get('discount_value', 0))}"),
                        platform="SHOPEE",
                        voucher_code=code,
                        verification_status=ver_status,
                        title=str(item.get("title", "Shopee Voucher")),
                        description=item.get("description"),
                        scope_type=scope,
                        discount_type=item.get("discount_type", "FIXED"),
                        discount_value=float(item.get("discount_value", 0)),
                        max_discount=float(item.get("max_discount")) if item.get("max_discount") is not None else None,
                        min_order_value=float(item.get("min_order_value", 0)),
                        start_time=start_t,
                        end_time=end_t,
                        status=VoucherStatus.UPCOMING_UNKNOWN_CODE if ver_status == VerificationStatus.UPCOMING_UNKNOWN_CODE else (VoucherStatus.UNVERIFIED if ver_status == VerificationStatus.UNVERIFIED else VoucherStatus.DISCOVERED),
                        is_freeship=0,
                        source_url=str(item.get("source_url") or item.get("claim_url") or "https://shopee.vn"),
                        source_type=str(item.get("source_type") or "COMMUNITY_FEED"),
                        source_title=item.get("source_title"),
                        source_captured_at=item.get("source_captured_at"),
                        source_evidence_excerpt=item.get("source_evidence_excerpt"),
                        percentage_used=item.get("percentage_used")
                    )
                    self.voucher_repo.upsert(rej_model)
                continue

            # 3. Xác định shop có được theo dõi không
            s_id = str(item.get("shop_id") or "").lower()
            s_name = str(item.get("shop_name") or "").lower()
            is_tracked = (s_id in tracked_shop_ids) or (s_name in tracked_shop_ids)

            # 4. Chấm điểm 0-100
            score, label, breakdown = calculate_elite_score(
                item,
                is_tracked_shop=is_tracked,
                is_personal_eligible=False
            )

            # Chỉ giữ voucher đạt ngưỡng (mặc định >= 80)
            if score < min_elite_score:
                items_rejected += 1
                continue

            # 5. Khởi tạo model Elite và trạng thái
            init_status = determine_initial_status(code, start_t, end_t, score)

            v_model = Voucher(
                id=str(item.get("id") or item.get("voucher_id") or f"ELITE_{code}_{int(item.get('discount_value', 0))}"),
                platform="SHOPEE",
                voucher_code=code,
                verification_status=ver_status,
                title=str(item.get("title", "Shopee Elite Voucher")),
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
                source_type=str(item.get("source_type") or "COMMUNITY_FEED"),
                source_title=item.get("source_title"),
                source_captured_at=item.get("source_captured_at"),
                source_evidence_excerpt=item.get("source_evidence_excerpt"),
                verified_at=item.get("verified_at"),
                last_checked_at=item.get("last_checked_at"),
                percentage_used=item.get("percentage_used"),
                confidence_score=score
            )

            if init_status in (VoucherStatus.UPCOMING_CODE_KNOWN, VoucherStatus.UPCOMING_UNKNOWN_CODE):
                elite_upcoming += 1

            # Lưu DB và phát hiện thay đổi
            res = self.voucher_repo.upsert(v_model)
            if res["is_new"]:
                elite_new += 1
                if v_model.status == VoucherStatus.UPCOMING_CODE_KNOWN:
                    events_to_notify.append({"type": "UPCOMING_KNOWN", "voucher": v_model, "score": score, "label": label})
                elif v_model.status == VoucherStatus.ACTIVE:
                    events_to_notify.append({"type": "ACTIVE_NEW", "voucher": v_model, "score": score, "label": label})
            else:
                if res["changes"]:
                    elite_updated += 1
                    code_change = next((c for c in res["changes"] if c["changed_field"] == "voucher_code"), None)
                    time_change = next((c for c in res["changes"] if c["changed_field"] in ("start_time", "end_time")), None)
                    val_change = next((c for c in res["changes"] if c["changed_field"] in ("discount_value", "min_order_value")), None)

                    if code_change:
                        events_to_notify.append({"type": "CODE_REVEALED", "voucher": v_model, "score": score, "change": code_change})
                    elif time_change:
                        events_to_notify.append({"type": "TIME_CHANGED", "voucher": v_model, "score": score, "change": time_change})
                    elif val_change:
                        events_to_notify.append({"type": "VALUE_CHANGED", "voucher": v_model, "score": score, "change": val_change})

        self.scan_repo.finish_scan_run(
            scan_id=scan_id,
            items_scanned=items_scanned,
            new_vouchers=elite_new,
            updated_vouchers=elite_updated,
            errors="; ".join(errors) if errors else None,
            rate_limit_state="NORMAL"
        )

        import os
        cookie_active = bool(os.environ.get("SHOPEE_COOKIE"))
        coverage_stats = {
            "cookie_enabled": cookie_active,
            "tracked_shops_count": len(tracked_shop_ids),
            "sources_scanned": sources_scanned,
            "errors_count": len(errors)
        }

        return {
            "scan_id": scan_id,
            "sources_count": sources_scanned,
            "items_scanned": items_scanned,
            "items_rejected": items_rejected,
            "elite_new": elite_new,
            "elite_updated": elite_updated,
            "elite_upcoming": elite_upcoming,
            "events_to_notify": events_to_notify,
            "errors": errors,
            "cookie_active": cookie_active,
            "coverage_stats": coverage_stats
        }
