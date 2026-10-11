import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from models.voucher import Voucher, ScopeType, VoucherStatus, VerificationStatus, DiscountType
from models.observation import VoucherObservation
from repositories.voucher_repository import VoucherRepository
from repositories.scan_repository import ScanRepository
from core.voucher_lifecycle import determine_initial_status

class DedupeService:
    def __init__(
        self,
        voucher_repo: Optional[Any] = None,
        scan_repo: Optional[ScanRepository] = None
    ):
        if isinstance(voucher_repo, ScanRepository):
            self.scan_repo = voucher_repo
            self.voucher_repo = VoucherRepository()
        else:
            self.voucher_repo = voucher_repo or VoucherRepository()
            self.scan_repo = scan_repo or ScanRepository()

    @staticmethod
    def calculate_fingerprint(voucher: Voucher, event_type: str = "") -> str:
        """
        Tính toán fingerprint:
        platform + voucher_code + scope_type + shop_id + start_time + end_time + discount_value + min_order_value + status (+ event_type)
        """
        code = str(voucher.voucher_code or "NO_CODE")
        stype = voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else str(voucher.scope_type)
        sid = str(voucher.shop_id or "NO_SHOP")
        status = voucher.status.value if isinstance(voucher.status, VoucherStatus) else str(voucher.status)
        raw_str = (
            f"{voucher.platform}_{code}_{stype}_{sid}_{voucher.start_time}_"
            f"{voucher.end_time}_{int(voucher.discount_value)}_{int(voucher.min_order_value)}_{status}_{event_type}"
        )
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def is_duplicate(self, fingerprint: str) -> bool:
        return self.scan_repo.is_notification_duplicate(fingerprint)

    @staticmethod
    def compute_payload_hash(data: Dict[str, Any]) -> str:
        """Tạo chuỗi hash SHA-256 từ payload quan sát để theo dõi thay đổi"""
        clean_dict = {k: v for k, v in data.items() if not k.startswith("_") and k != "observed_at"}
        payload_str = json.dumps(clean_dict, sort_keys=True, default=str)
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_canonical_id(
        platform: str,
        voucher_code: Optional[str] = None,
        scope_type: str = "PLATFORM",
        shop_id: Optional[str] = None,
        platform_voucher_id: Optional[str] = None,
        claim_url: Optional[str] = None,
        discount_value: float = 0,
        min_order_value: float = 0,
        start_time: str = ""
    ) -> str:
        """
        Sinh Canonical ID chuẩn hóa theo thứ tự ưu tiên:
        1. platform + platform_voucher_id
        2. platform + normalized_code + scope + shop_id
        3. platform + url_hash + discount + min_order
        Tuyệt đối KHÔNG sinh UUID ngẫu nhiên hay gán ngày vào ID nếu voucher nhiều ngày.
        """
        p = platform.upper()
        if platform_voucher_id and str(platform_voucher_id).strip():
            return f"CANON_{p}_ID_{platform_voucher_id.strip()}"

        if voucher_code and voucher_code.strip():
            clean_code = voucher_code.strip().upper()
            scope_tag = str(shop_id).strip() if (scope_type == "SHOP" and shop_id) else scope_type.upper()
            return f"CANON_{p}_{scope_tag}_{clean_code}"

        # Voucher không code ("Lưu ngay"): kết hợp scope_tag và start_time để tránh gộp nhầm qua ngày/qua shop
        url_hash = hashlib.md5((claim_url or "NO_URL").encode("utf-8")).hexdigest()[:8]
        scope_tag = str(shop_id).strip() if (scope_type == "SHOP" and shop_id) else scope_type.upper()
        time_tag = start_time.strip().replace(" ", "_").replace(":", "").replace("/", "") if start_time else "NOTIME"
        return f"CANON_{p}_{scope_tag}_NOC_{url_hash}_{int(discount_value)}_{int(min_order_value)}_{time_tag}"

    def process_observation(
        self,
        raw_item: Dict[str, Any],
        source_name: str,
        source_type: str
    ) -> Tuple[Voucher, VoucherObservation, bool, bool]:
        """
        Quy trình xử lý quan sát thô theo mô hình Canonical:
        1. Tìm match Canonical hiện có qua find_canonical_match.
        2. Nếu chưa có -> Tạo Canonical Voucher mới.
        3. Nếu đã có -> Hợp nhất bằng chứng, cập nhật thời gian, lộ code nếu có.
        4. Tạo bản ghi VoucherObservation và ghi nhận vào DB.
        Trả về: (canonical_voucher, observation, is_new_canonical, has_revealed_code)
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        platform = raw_item.get("platform", "SHOPEE").upper()
        code = raw_item.get("voucher_code")
        p_vid = raw_item.get("platform_voucher_id")
        scope_str = str(raw_item.get("scope_type", "PLATFORM")).upper()
        shop_id = raw_item.get("shop_id")
        start_t = str(raw_item.get("start_time", ""))
        end_t = str(raw_item.get("end_time", ""))
        claim_url = raw_item.get("source_url") or raw_item.get("claim_url")
        d_val = float(raw_item.get("discount_value", 0) or 0)
        min_sp = float(raw_item.get("min_order_value", 0) or 0)
        max_d = float(raw_item.get("max_discount", 0) or d_val) if raw_item.get("max_discount") is not None else None
        claim_type = raw_item.get("claim_type", "CODE" if code else "SAVE_BUTTON")
        payload_hash = self.compute_payload_hash(raw_item)

        # 1. Tìm kiếm canonical voucher đã tồn tại
        existing_canonical = self.voucher_repo.find_canonical_match(
            platform=platform,
            voucher_code=code,
            scope_type=scope_str,
            shop_id=shop_id,
            start_time=start_t,
            platform_voucher_id=p_vid,
            claim_url=claim_url,
            discount_value=d_val,
            min_order_value=min_sp
        )

        is_new = False
        revealed_code = False

        if not existing_canonical:
            # Tạo Canonical Voucher mới
            canonical_id = self.generate_canonical_id(
                platform=platform,
                voucher_code=code,
                scope_type=scope_str,
                shop_id=shop_id,
                platform_voucher_id=p_vid,
                claim_url=claim_url,
                discount_value=d_val,
                min_order_value=min_sp,
                start_time=start_t
            )

            # Khởi tạo ScopeType & DiscountType
            scope_type_enum = ScopeType.SHOP if (scope_str == "SHOP" or shop_id) else (ScopeType.CATEGORY if "CAT" in scope_str else ScopeType.PLATFORM)
            dtype_enum = DiscountType.PERCENT if raw_item.get("discount_type") == "PERCENT" else DiscountType.FIXED
            
            # Trạng thái xác minh
            v_status_str = raw_item.get("verification_status", "UNVERIFIED")
            try:
                v_status_enum = VerificationStatus(v_status_str)
            except ValueError:
                v_status_enum = VerificationStatus.UNVERIFIED

            # Xác định trạng thái vòng đời ban đầu chuẩn (ACTIVE, UPCOMING, EXPIRED...)
            init_status = determine_initial_status(
                voucher_code=code,
                start_time_str=start_t,
                end_time_str=end_t,
                confidence_score=int(raw_item.get("confidence_score", 90)),
                claim_type=claim_type
            )

            canonical_voucher = Voucher(
                id=canonical_id,
                platform=platform,
                platform_voucher_id=p_vid,
                voucher_code=code,
                claim_type=claim_type,
                title=raw_item.get("title", f"Voucher {platform}"),
                description=raw_item.get("description"),
                scope_type=scope_type_enum,
                shop_id=shop_id,
                shop_name=raw_item.get("shop_name"),
                shop_url=raw_item.get("shop_url"),
                discount_type=dtype_enum,
                discount_value=d_val,
                max_discount=max_d,
                min_order_value=min_sp,
                start_time=start_t,
                end_time=end_t,
                source_url=claim_url or "https://shopee.vn",
                source_type=source_type,
                source_title=raw_item.get("source_title"),
                source_captured_at=raw_item.get("source_captured_at", now_iso),
                source_evidence_excerpt=raw_item.get("source_evidence_excerpt"),
                verification_status=v_status_enum,
                confidence_score=int(raw_item.get("confidence_score", 90)),
                is_freeship=int(raw_item.get("is_freeship", 0)),
                status=init_status,
                first_seen_at=now_iso,
                last_seen_at=now_iso,
                verified_at=raw_item.get("verified_at"),
                created_at=now_iso,
                updated_at=now_iso
            )
            self.voucher_repo.upsert(canonical_voucher)
            is_new = True
        else:
            canonical_voucher = existing_canonical
            # Kiểm tra trường hợp lộ mã (trước đây không có code, nay có code)
            if not canonical_voucher.voucher_code and code:
                canonical_voucher.voucher_code = code
                canonical_voucher.claim_type = "CODE"
                canonical_voucher.status = determine_initial_status(
                    voucher_code=code,
                    start_time_str=canonical_voucher.start_time,
                    end_time_str=canonical_voucher.end_time,
                    confidence_score=canonical_voucher.confidence_score,
                    claim_type="CODE"
                )
                revealed_code = True

            # Cập nhật thông tin thời gian và bằng chứng mới nhất
            canonical_voucher.last_seen_at = now_iso
            canonical_voucher.updated_at = now_iso
            if raw_item.get("source_evidence_excerpt"):
                canonical_voucher.source_evidence_excerpt = raw_item["source_evidence_excerpt"]
            self.voucher_repo.upsert(canonical_voucher)

        # 2. Tạo và lưu bản ghi VoucherObservation
        obs = VoucherObservation(
            id=f"OBS_{int(datetime.now(timezone.utc).timestamp()*1000)}_{uuid.uuid4().hex[:6]}",
            canonical_id=canonical_voucher.id,
            source_name=source_name,
            source_type=source_type,
            source_url=claim_url or "https://shopee.vn",
            raw_code=code,
            claim_type=claim_type,
            discount_amount=d_val if raw_item.get("discount_type") != "PERCENT" else None,
            discount_percent=d_val if raw_item.get("discount_type") == "PERCENT" else None,
            min_order_value=min_sp,
            max_discount=max_d,
            observed_at=now_iso,
            raw_payload_hash=payload_hash,
            evidence_excerpt=raw_item.get("source_evidence_excerpt"),
            http_status=200
        )
        self.voucher_repo.add_observation(obs)

        return canonical_voucher, obs, is_new, revealed_code
