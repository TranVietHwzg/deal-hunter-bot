import json
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from repositories.base_repository import BaseRepository
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from models.observation import VoucherObservation
from models.source_run import SourceRun

class VoucherRepository(BaseRepository):
    def __init__(self, db_path: Optional[str] = None):
        if db_path is not None:
            super().__init__(db_path)
        else:
            super().__init__()
        self.init_schema()

    def init_schema(self) -> None:
        """Đảm bảo các bảng vouchers và voucher_changes đã tồn tại theo schema mới"""
        with self.transaction() as cur:
            # 1. Bảng vouchers
            cur.execute("""
            CREATE TABLE IF NOT EXISTS vouchers (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL DEFAULT 'SHOPEE',
                voucher_code TEXT,
                title TEXT NOT NULL DEFAULT '',
                description TEXT,
                scope_type TEXT DEFAULT 'PLATFORM',
                shop_id TEXT,
                shop_name TEXT,
                shop_url TEXT,
                category_names TEXT,
                discount_type TEXT DEFAULT 'FIXED',
                discount_value REAL DEFAULT 0,
                max_discount REAL,
                min_order_value REAL DEFAULT 0,
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
                status TEXT DEFAULT 'DISCOVERED',
                is_freeship INTEGER DEFAULT 0,
                source_url TEXT DEFAULT 'https://shopee.vn',
                source_type TEXT DEFAULT 'CAMPAIGN_PAGE',
                confidence_score INTEGER DEFAULT 90,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT chk_no_freeship CHECK (is_freeship = 0)
            );
            """)

            # Đảm bảo các cột mới có mặt nếu bảng đã tồn tại từ trước
            cols = [c[1] for c in cur.execute("PRAGMA table_info(vouchers)").fetchall()]
            new_cols = {
                "platform": "TEXT DEFAULT 'SHOPEE'",
                "platform_id": "TEXT DEFAULT 'SHOPEE'",
                "voucher_id_on_platform": "TEXT",
                "voucher_type": "TEXT DEFAULT 'PLATFORM'",
                "category": "TEXT",
                "scope_type": "TEXT DEFAULT 'PLATFORM'",
                "shop_url": "TEXT",
                "category_names": "TEXT",
                "max_discount": "REAL",
                "max_discount_amount": "REAL",
                "min_spend": "REAL DEFAULT 0",
                "min_order_value": "REAL DEFAULT 0",
                "claim_url": "TEXT DEFAULT 'https://shopee.vn'",
                "timezone": "TEXT DEFAULT 'Asia/Ho_Chi_Minh'",
                "source_url": "TEXT DEFAULT 'https://shopee.vn'",
                "source_type": "TEXT DEFAULT 'CAMPAIGN_PAGE'",
                "confidence_score": "INTEGER DEFAULT 90",
                "first_seen_at": "TEXT",
                "last_seen_at": "TEXT",
                "is_hidden": "INTEGER DEFAULT 0",
                "quality_score": "INTEGER DEFAULT 0",
                "is_hot": "INTEGER DEFAULT 0",
                "verification_status": "TEXT DEFAULT 'UNVERIFIED'",
                "source_title": "TEXT",
                "source_captured_at": "TEXT",
                "source_evidence_excerpt": "TEXT",
                "verified_at": "TEXT",
                "last_checked_at": "TEXT",
                "percentage_used": "REAL",
                "platform_voucher_id": "TEXT",
                "claim_type": "TEXT DEFAULT 'CODE'",
                "verification_level": "TEXT DEFAULT 'OBSERVED_PUBLIC'",
                "eligibility_status": "TEXT DEFAULT 'PERSONAL_UNKNOWN'",
                "quality_tags": "TEXT",
                "evidence_score": "INTEGER DEFAULT 50",
                "guide": "TEXT",
                "last_verified_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            }
            for col_name, col_type in new_cols.items():
                if col_name not in cols:
                    try:
                        cur.execute(f"ALTER TABLE vouchers ADD COLUMN {col_name} {col_type};")
                    except Exception as e:
                        print(f"[VoucherRepository] Lưu ý khi thêm cột {col_name}: {e}")

            try:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_platform_voucher ON vouchers(platform_id, voucher_id_on_platform);")
            except Exception:
                pass

            # 2. Bảng voucher_changes
            cur.execute("""
            CREATE TABLE IF NOT EXISTS voucher_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_id TEXT NOT NULL,
                changed_field TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_url TEXT,
                FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
            );
            """)

            # 3. Bảng voucher_observations (Lưu mọi quan sát đa nguồn)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS voucher_observations (
                id TEXT PRIMARY KEY,
                canonical_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT NOT NULL,
                raw_code TEXT,
                claim_type TEXT NOT NULL DEFAULT 'CODE',
                discount_amount REAL,
                discount_percent REAL,
                min_order_value REAL NOT NULL DEFAULT 0,
                max_discount REAL,
                observed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                raw_payload_hash TEXT NOT NULL,
                evidence_excerpt TEXT,
                http_status INTEGER NOT NULL DEFAULT 200,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (canonical_id) REFERENCES vouchers(id) ON DELETE CASCADE
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_obs_canonical ON voucher_observations(canonical_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_obs_source ON voucher_observations(source_name, observed_at);")

            # 4. Bảng source_runs (Sức khỏe và metrics từng lượt cào)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS source_runs (
                id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP NOT NULL,
                pages_requested INTEGER NOT NULL DEFAULT 1,
                http_success_count INTEGER NOT NULL DEFAULT 0,
                http_failure_count INTEGER NOT NULL DEFAULT 0,
                items_raw INTEGER NOT NULL DEFAULT 0,
                items_normalized INTEGER NOT NULL DEFAULT 0,
                items_new INTEGER NOT NULL DEFAULT 0,
                items_updated INTEGER NOT NULL DEFAULT 0,
                items_rejected_by_rule INTEGER NOT NULL DEFAULT 0,
                latest_source_timestamp TEXT,
                parser_version TEXT NOT NULL DEFAULT '1.0.0',
                status TEXT NOT NULL,
                error_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_source_runs_name ON source_runs(source_name, started_at DESC);")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vouchers_start_time ON vouchers(start_time);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vouchers_scope ON vouchers(scope_type, shop_id);")

    def _row_to_voucher(self, row: Dict[str, Any]) -> Voucher:
        cat_names = []
        if row.get("category_names"):
            try:
                cat_names = json.loads(row["category_names"])
            except Exception:
                cat_names = [str(row["category_names"])]

        # Chuyển đổi an toàn ScopeType
        raw_scope = str(row.get("scope_type") or row.get("voucher_type") or "PLATFORM").upper()
        if "SHOP" in raw_scope or row.get("shop_id"):
            scope_val = ScopeType.SHOP
        elif "CAT" in raw_scope or "LIVE" in raw_scope:
            scope_val = ScopeType.CATEGORY
        else:
            scope_val = ScopeType.PLATFORM

        # Chuyển đổi an toàn DiscountType
        raw_dtype = str(row.get("discount_type") or "FIXED").upper()
        if "PERCENT" in raw_dtype:
            dtype_val = DiscountType.PERCENT
        else:
            dtype_val = DiscountType.FIXED

        # Chuyển đổi an toàn VoucherStatus
        raw_status = str(row.get("status") or "DISCOVERED").upper()
        status_map = {
            "DISCOVERED": VoucherStatus.DISCOVERED,
            "UPCOMING_UNKNOWN_CODE": VoucherStatus.UPCOMING_UNKNOWN_CODE,
            "UPCOMING_CODE_KNOWN": VoucherStatus.UPCOMING_CODE_KNOWN,
            "UPCOMING": VoucherStatus.UPCOMING_CODE_KNOWN,
            "ACTIVE": VoucherStatus.ACTIVE,
            "RESTOCKED": VoucherStatus.ACTIVE,
            "EXHAUSTED": VoucherStatus.EXHAUSTED,
            "EXPIRED": VoucherStatus.EXPIRED,
            "CANCELLED": VoucherStatus.CANCELLED,
            "UNVERIFIED": VoucherStatus.UNVERIFIED,
        }
        status_val = status_map.get(raw_status, VoucherStatus.DISCOVERED)

        raw_vstatus = str(row.get("verification_status") or "UNVERIFIED").upper()
        try:
            vstatus_val = VerificationStatus(raw_vstatus)
        except ValueError:
            vstatus_val = VerificationStatus.UNVERIFIED

        return Voucher(
            id=row["id"],
            platform=row.get("platform") or "SHOPEE",
            voucher_code=row.get("voucher_code"),
            verification_status=vstatus_val,
            title=row["title"],
            description=row.get("description"),
            scope_type=scope_val,
            shop_id=row.get("shop_id"),
            shop_name=row.get("shop_name"),
            shop_url=row.get("shop_url"),
            category_names=cat_names,
            discount_type=dtype_val,
            discount_value=float(row.get("discount_value") or 0),
            max_discount=float(row["max_discount"]) if row.get("max_discount") is not None else None,
            min_order_value=float(row.get("min_order_value") or row.get("min_spend") or 0),
            start_time=str(row.get("start_time") or ""),
            end_time=str(row.get("end_time") or ""),
            timezone=row.get("timezone") or "Asia/Ho_Chi_Minh",
            status=status_val,
            is_freeship=int(row.get("is_freeship") or 0),
            source_url=row.get("source_url") or row.get("claim_url") or "https://shopee.vn",
            source_type=row.get("source_type") or "CAMPAIGN_PAGE",
            source_title=row.get("source_title"),
            source_captured_at=row.get("source_captured_at"),
            source_evidence_excerpt=row.get("source_evidence_excerpt"),
            confidence_score=int(row.get("confidence_score") or 90),
            first_seen_at=row.get("first_seen_at"),
            last_seen_at=row.get("last_seen_at"),
            verified_at=row.get("verified_at"),
            last_checked_at=row.get("last_checked_at"),
            percentage_used=float(row["percentage_used"]) if row.get("percentage_used") is not None else None,
            platform_voucher_id=row.get("platform_voucher_id") or row.get("voucher_id_on_platform"),
            claim_type=str(row.get("claim_type") or "CODE"),
            verification_level=str(row.get("verification_level") or "OBSERVED_PUBLIC"),
            eligibility_status=str(row.get("eligibility_status") or "PERSONAL_UNKNOWN"),
            quality_tags=json.loads(row["quality_tags"]) if row.get("quality_tags") and isinstance(row["quality_tags"], str) and row["quality_tags"].startswith("[") else [],
            evidence_score=int(row.get("evidence_score") or 50),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at")
        )

    def get_by_id(self, voucher_id: str) -> Optional[Voucher]:
        with self.transaction() as cur:
            row = cur.execute("SELECT * FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
            if row:
                return self._row_to_voucher(dict(row))
        return None

    def upsert(self, voucher: Voucher) -> Dict[str, Any]:
        """
        Lưu voucher vào DB. Nếu đã tồn tại, phát hiện các trường thay đổi
        (voucher_code, start_time, end_time, discount_value, min_order_value, status)
        và ghi vào bảng voucher_changes.
        Trả về dict: {"is_new": bool, "changes": List[Dict[str, Any]]}
        """
        if voucher.is_freeship != 0:
            return {"is_new": False, "changes": []}

        if voucher.percentage_used is None and voucher.source_evidence_excerpt:
            m_pct = re.search(r'Đã dùng:\s*(\d+(?:\.\d+)?)\s*%', voucher.source_evidence_excerpt)
            if m_pct:
                try:
                    voucher.percentage_used = float(m_pct.group(1))
                except Exception:
                    pass

        existing = self.get_by_id(voucher.id)
        changes = []

        now_str = datetime.now(timezone.utc).isoformat()
        cat_json = json.dumps(voucher.category_names, ensure_ascii=False)

        with self.transaction() as cur:
            if existing:
                # So sánh các trường quan trọng
                fields_to_track = [
                    ("voucher_code", existing.voucher_code, voucher.voucher_code),
                    ("start_time", existing.start_time, voucher.start_time),
                    ("end_time", existing.end_time, voucher.end_time),
                    ("discount_value", existing.discount_value, voucher.discount_value),
                    ("min_order_value", existing.min_order_value, voucher.min_order_value),
                    ("status", existing.status.value, voucher.status.value if isinstance(voucher.status, VoucherStatus) else voucher.status)
                ]
                for field_name, old_val, new_val in fields_to_track:
                    if old_val != new_val and new_val is not None:
                        changes.append({
                            "voucher_id": voucher.id,
                            "changed_field": field_name,
                            "old_value": str(old_val),
                            "new_value": str(new_val),
                            "source_url": voucher.source_url
                        })
                        cur.execute("""
                        INSERT INTO voucher_changes (voucher_id, changed_field, old_value, new_value, source_url)
                        VALUES (?, ?, ?, ?, ?)
                        """, (voucher.id, field_name, str(old_val), str(new_val), voucher.source_url))

                # Cập nhật bản ghi hiện có
                actual_cols = set([c[1] for c in cur.execute("PRAGMA table_info(vouchers)").fetchall()])
                cols_to_save = {
                    "voucher_code": voucher.voucher_code,
                    "title": voucher.title,
                    "description": voucher.description,
                    "scope_type": voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else voucher.scope_type,
                    "voucher_type": voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else voucher.scope_type,
                    "shop_id": voucher.shop_id,
                    "shop_name": voucher.shop_name,
                    "shop_url": voucher.shop_url,
                    "category_names": cat_json,
                    "category": voucher.category_names[0] if voucher.category_names else None,
                    "discount_type": voucher.discount_type.value if isinstance(voucher.discount_type, DiscountType) else voucher.discount_type,
                    "discount_value": voucher.discount_value,
                    "max_discount": voucher.max_discount,
                    "max_discount_amount": voucher.max_discount or voucher.discount_value,
                    "min_order_value": voucher.min_order_value,
                    "min_spend": voucher.min_order_value,
                    "start_time": voucher.start_time,
                    "end_time": voucher.end_time,
                    "timezone": voucher.timezone,
                    "status": voucher.status.value if isinstance(voucher.status, VoucherStatus) else voucher.status,
                    "verification_status": voucher.verification_status.value if isinstance(voucher.verification_status, VerificationStatus) else str(voucher.verification_status),
                    "source_title": voucher.source_title,
                    "source_captured_at": voucher.source_captured_at,
                    "source_evidence_excerpt": voucher.source_evidence_excerpt,
                    "verified_at": voucher.verified_at,
                    "last_checked_at": voucher.last_checked_at or datetime.now(timezone.utc).isoformat(),
                    "percentage_used": voucher.percentage_used,
                    "platform_voucher_id": voucher.platform_voucher_id,
                    "claim_type": voucher.claim_type,
                    "verification_level": voucher.verification_level,
                    "eligibility_status": voucher.eligibility_status,
                    "quality_tags": json.dumps(voucher.quality_tags, ensure_ascii=False) if voucher.quality_tags else None,
                    "evidence_score": voucher.evidence_score,
                    "claim_url": voucher.source_url,
                    "source_url": voucher.source_url,
                    "source_type": voucher.source_type,
                    "confidence_score": voucher.confidence_score,
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

                update_keys = [k for k in cols_to_save.keys() if k in actual_cols]
                set_clause = ", ".join([f"{k} = ?" for k in update_keys])
                update_vals = [cols_to_save[k] for k in update_keys] + [voucher.id]
                cur.execute(f"UPDATE vouchers SET {set_clause} WHERE id = ?", tuple(update_vals))
                return {"is_new": False, "changes": changes}
            else:
                # Thêm mới
                actual_cols = set([c[1] for c in cur.execute("PRAGMA table_info(vouchers)").fetchall()])
                cols_to_save = {
                    "id": voucher.id,
                    "platform": voucher.platform,
                    "platform_id": voucher.platform,
                    "voucher_id_on_platform": voucher.platform_voucher_id or voucher.id,
                    "platform_voucher_id": voucher.platform_voucher_id,
                    "voucher_code": voucher.voucher_code,
                    "claim_type": voucher.claim_type,
                    "verification_level": voucher.verification_level,
                    "eligibility_status": voucher.eligibility_status,
                    "quality_tags": json.dumps(voucher.quality_tags, ensure_ascii=False) if voucher.quality_tags else None,
                    "evidence_score": voucher.evidence_score,
                    "verification_status": voucher.verification_status.value if isinstance(voucher.verification_status, VerificationStatus) else str(voucher.verification_status),
                    "title": voucher.title,
                    "description": voucher.description,
                    "scope_type": voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else voucher.scope_type,
                    "voucher_type": voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else voucher.scope_type,
                    "shop_id": voucher.shop_id,
                    "shop_name": voucher.shop_name,
                    "shop_url": voucher.shop_url,
                    "category_names": cat_json,
                    "category": voucher.category_names[0] if voucher.category_names else None,
                    "discount_type": voucher.discount_type.value if isinstance(voucher.discount_type, DiscountType) else voucher.discount_type,
                    "discount_value": voucher.discount_value,
                    "max_discount": voucher.max_discount,
                    "max_discount_amount": voucher.max_discount or voucher.discount_value,
                    "min_order_value": voucher.min_order_value,
                    "min_spend": voucher.min_order_value,
                    "start_time": voucher.start_time,
                    "end_time": voucher.end_time,
                    "timezone": voucher.timezone,
                    "status": voucher.status.value if isinstance(voucher.status, VoucherStatus) else voucher.status,
                    "is_freeship": 0,
                    "claim_url": voucher.source_url,
                    "source_url": voucher.source_url,
                    "source_type": voucher.source_type,
                    "source_title": voucher.source_title,
                    "source_captured_at": voucher.source_captured_at,
                    "source_evidence_excerpt": voucher.source_evidence_excerpt,
                    "verified_at": voucher.verified_at,
                    "last_checked_at": voucher.last_checked_at or datetime.now(timezone.utc).isoformat(),
                    "percentage_used": voucher.percentage_used,
                    "confidence_score": voucher.confidence_score,
                    "first_seen_at": datetime.now(timezone.utc).isoformat(),
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

                insert_keys = [k for k in cols_to_save.keys() if k in actual_cols]
                insert_vals = [cols_to_save[k] for k in insert_keys]
                placeholders = ", ".join(["?"] * len(insert_keys))
                cur.execute(f"INSERT INTO vouchers ({', '.join(insert_keys)}) VALUES ({placeholders})", tuple(insert_vals))
                return {"is_new": True, "changes": []}

    def update_status(self, voucher_id: str, new_status: VoucherStatus) -> bool:
        """Cập nhật trạng thái voucher và ghi vào voucher_changes"""
        existing = self.get_by_id(voucher_id)
        if not existing:
            return False
        if existing.status == new_status:
            return True

        with self.transaction() as cur:
            cur.execute("""
            INSERT INTO voucher_changes (voucher_id, changed_field, old_value, new_value, source_url)
            VALUES (?, 'status', ?, ?, ?)
            """, (voucher_id, existing.status.value, new_status.value, existing.source_url))

            cur.execute("""
            UPDATE vouchers SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (new_status.value, voucher_id))
        return True

    def get_vouchers(
        self,
        status: Optional[VoucherStatus] = None,
        scope_type: Optional[ScopeType] = None,
        shop_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Voucher]:
        sql = "SELECT * FROM vouchers WHERE is_freeship = 0"
        params = []
        if status:
            sql += " AND status = ?"
            params.append(status.value if isinstance(status, VoucherStatus) else status)
        if scope_type:
            sql += " AND scope_type = ?"
            params.append(scope_type.value if isinstance(scope_type, ScopeType) else scope_type)
        if shop_id:
            sql += " AND shop_id = ?"
            params.append(shop_id)

        sql += " ORDER BY (status = 'ACTIVE') DESC, (status = 'UPCOMING_CODE_KNOWN') DESC, start_time ASC, discount_value DESC LIMIT ?"
        params.append(limit)

        with self.transaction() as cur:
            rows = cur.execute(sql, tuple(params)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_upcoming_vouchers(self, days: int = 7, limit: int = 200) -> List[Voucher]:
        """Lấy các voucher sắp mở trong N ngày tới (giới hạn LIMIT để tối ưu RAM 512MB)"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND status IN ('UPCOMING_CODE_KNOWN', 'UPCOMING_UNKNOWN_CODE')
            ORDER BY start_time ASC, discount_value DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_active_vouchers(self, limit: int = 200) -> List[Voucher]:
        """Lấy các voucher đang ACTIVE (giới hạn LIMIT để tối ưu RAM 512MB)"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND status = 'ACTIVE'
            ORDER BY discount_value DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_all_vouchers(self, limit: int = 100) -> List[Voucher]:
        """Lấy tất cả vouchers không phải freeship"""
        return self.get_vouchers(limit=limit)

    def get_by_code(self, voucher_code: str) -> Optional[Voucher]:
        """Tìm voucher theo mã code chính xác"""
        if not voucher_code:
            return None
        code_clean = str(voucher_code).strip().upper()
        with self.transaction() as cur:
            row = cur.execute(
                "SELECT * FROM vouchers WHERE UPPER(voucher_code) = ? LIMIT 1",
                (code_clean,)
            ).fetchone()
            if row:
                return self._row_to_voucher(dict(row))
        return None

    def get_active_zero_dong_vouchers(self, limit: int = 20) -> List[Voucher]:
        """Lấy danh sách mã ĐƠN 0Đ đang ACTIVE, giảm >= 30k cố định hoặc >= 30%, chưa hết lượt (< 90%)"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND (min_order_value = 0 OR min_spend = 0)
              AND (
                (discount_type IN ('FIXED', 'FIXED_AMOUNT') AND discount_value >= 30000) OR
                (discount_type IN ('PERCENT', 'PERCENTAGE') AND discount_value >= 30 AND (max_discount IS NULL OR max_discount >= 30000))
              )
              AND status = 'ACTIVE'
              AND (percentage_used IS NULL OR percentage_used < 90.0)
            ORDER BY discount_value DESC, max_discount DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_upcoming_zero_dong_vouchers(self, days: int = 1, limit: int = 30) -> List[Voucher]:
        """Lấy danh sách mã ĐƠN 0Đ sắp mở trong khung giờ tới"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND (min_order_value = 0 OR min_spend = 0)
              AND (
                (discount_type IN ('FIXED', 'FIXED_AMOUNT') AND discount_value >= 30000) OR
                (discount_type IN ('PERCENT', 'PERCENTAGE') AND discount_value >= 30 AND (max_discount IS NULL OR max_discount >= 30000))
              )
              AND status IN ('UPCOMING_CODE_KNOWN', 'UPCOMING_UNKNOWN_CODE', 'UPCOMING')
              AND (percentage_used IS NULL OR percentage_used < 90.0)
            ORDER BY start_time ASC, discount_value DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_elite_verified_vouchers(self, limit: int = 50) -> List[Voucher]:
        """Lấy danh sách voucher đạt chuẩn xác minh VERIFIED_ACTIVE, VERIFIED_UPCOMING hoặc COMMUNITY_LEAK"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND verification_status IN ('VERIFIED_ACTIVE', 'VERIFIED_UPCOMING', 'COMMUNITY_LEAK')
              AND status NOT IN ('EXHAUSTED', 'EXPIRED', 'CANCELLED')
            ORDER BY (verification_status = 'VERIFIED_ACTIVE') DESC, discount_value DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_community_leak_vouchers(self, limit: int = 50) -> List[Voucher]:
        """Lấy danh sách mã leak cộng đồng (COMMUNITY_LEAK) chờ test"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND verification_status = 'COMMUNITY_LEAK'
              AND status NOT IN ('EXHAUSTED', 'EXPIRED', 'CANCELLED')
            ORDER BY discount_value DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_unverified_vouchers(self, limit: int = 50) -> List[Voucher]:
        """Lấy danh sách voucher UNVERIFIED đang chờ kiểm tra"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND verification_status = 'UNVERIFIED'
            ORDER BY discount_value DESC
            LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_verification_audit_summary(self) -> Dict[str, int]:
        """Thống kê số lượng voucher theo từng trạng thái xác minh"""
        summary = {
            "VERIFIED_ACTIVE": 0,
            "VERIFIED_UPCOMING": 0,
            "UPCOMING_UNKNOWN_CODE": 0,
            "PERSONAL_ELIGIBILITY_UNKNOWN": 0,
            "COMMUNITY_LEAK": 0,
            "UNVERIFIED": 0,
            "INVALID": 0,
            "TEST_DATA": 0,
            "TOTAL": 0
        }
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT verification_status, count(*) as cnt 
            FROM vouchers 
            GROUP BY verification_status
            """).fetchall()
            for r in rows:
                st = str(r["verification_status"] or "UNVERIFIED")
                count = int(r["cnt"])
                summary[st] = count
                summary["TOTAL"] += count
        return summary

    # -------------------------------------------------------------
    # 5. Quan sát đa nguồn (Observations) & Sức khỏe nguồn (Source Runs)
    # -------------------------------------------------------------
    def add_observation(self, obs: VoucherObservation) -> bool:
        """Ghi nhận một lần quan sát voucher từ một nguồn cụ thể (không ghi đè mất bằng chứng)"""
        with self.transaction() as cur:
            cur.execute("""
            INSERT INTO voucher_observations (
                id, canonical_id, source_name, source_type, source_url,
                raw_code, claim_type, discount_amount, discount_percent,
                min_order_value, max_discount, observed_at, raw_payload_hash,
                evidence_excerpt, http_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obs.id, obs.canonical_id, obs.source_name, obs.source_type, obs.source_url,
                obs.raw_code, obs.claim_type, obs.discount_amount, obs.discount_percent,
                obs.min_order_value, obs.max_discount, obs.observed_at, obs.raw_payload_hash,
                obs.evidence_excerpt, obs.http_status, obs.created_at
            ))
            return True

    def get_observations(self, canonical_id: str) -> List[VoucherObservation]:
        """Lấy toàn bộ các lần quan sát của voucher canonical này"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM voucher_observations 
            WHERE canonical_id = ? 
            ORDER BY observed_at DESC
            """, (canonical_id,)).fetchall()
            return [
                VoucherObservation(
                    id=r["id"],
                    canonical_id=r["canonical_id"],
                    source_name=r["source_name"],
                    source_type=r["source_type"],
                    source_url=r["source_url"],
                    raw_code=r["raw_code"],
                    claim_type=r["claim_type"],
                    discount_amount=r["discount_amount"],
                    discount_percent=r["discount_percent"],
                    min_order_value=float(r["min_order_value"] or 0),
                    max_discount=r["max_discount"],
                    observed_at=r["observed_at"],
                    raw_payload_hash=r["raw_payload_hash"],
                    evidence_excerpt=r["evidence_excerpt"],
                    http_status=int(r["http_status"] or 200),
                    created_at=r["created_at"]
                ) for r in rows
            ]

    def record_source_run(self, run: SourceRun) -> bool:
        """Ghi nhận kết quả một chu kỳ quét của nguồn"""
        with self.transaction() as cur:
            cur.execute("""
            INSERT INTO source_runs (
                id, source_name, started_at, finished_at, pages_requested,
                http_success_count, http_failure_count, items_raw, items_normalized,
                items_new, items_updated, items_rejected_by_rule, latest_source_timestamp,
                parser_version, status, error_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.id, run.source_name, run.started_at, run.finished_at, run.pages_requested,
                run.http_success_count, run.http_failure_count, run.items_raw, run.items_normalized,
                run.items_new, run.items_updated, run.items_rejected_by_rule, run.latest_source_timestamp,
                run.parser_version, run.status, run.error_summary, run.created_at
            ))
            return True

    def get_latest_source_runs(self, limit: int = 10) -> List[SourceRun]:
        """Lấy lịch sử các lần chạy gần nhất của các nguồn"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM source_runs ORDER BY started_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [
                SourceRun(
                    id=r["id"],
                    source_name=r["source_name"],
                    started_at=r["started_at"],
                    finished_at=r["finished_at"],
                    pages_requested=r["pages_requested"],
                    http_success_count=r["http_success_count"],
                    http_failure_count=r["http_failure_count"],
                    items_raw=r["items_raw"],
                    items_normalized=r["items_normalized"],
                    items_new=r["items_new"],
                    items_updated=r["items_updated"],
                    items_rejected_by_rule=r["items_rejected_by_rule"],
                    latest_source_timestamp=r["latest_source_timestamp"],
                    parser_version=r["parser_version"],
                    status=r["status"],
                    error_summary=r["error_summary"],
                    created_at=r["created_at"]
                ) for r in rows
            ]

    def get_source_health_summary(self) -> Dict[str, Any]:
        """Tóm tắt sức khỏe mới nhất của tất cả các nguồn"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT sr.* FROM source_runs sr
            INNER JOIN (
                SELECT source_name, MAX(started_at) as max_started
                FROM source_runs GROUP BY source_name
            ) latest ON sr.source_name = latest.source_name AND sr.started_at = latest.max_started
            """).fetchall()
            return {
                r["source_name"]: {
                    "status": r["status"],
                    "items_raw": r["items_raw"],
                    "items_normalized": r["items_normalized"],
                    "started_at": r["started_at"],
                    "error_summary": r["error_summary"]
                } for r in rows
            }

    def find_canonical_match(
        self,
        platform: str,
        voucher_code: Optional[str] = None,
        scope_type: Optional[str] = None,
        shop_id: Optional[str] = None,
        start_time: Optional[str] = None,
        platform_voucher_id: Optional[str] = None,
        claim_url: Optional[str] = None,
        discount_value: float = 0,
        min_order_value: float = 0
    ) -> Optional[Voucher]:
        """
        Tìm kiếm voucher Canonical hiện có theo thứ tự ưu tiên định danh:
        1. platform + platform_voucher_id
        2. platform + normalized_code + scope + shop_id
        3. platform + claim_url + discount + min_order
        """
        with self.transaction() as cur:
            # 1. Trùng platform_voucher_id
            if platform_voucher_id:
                row = cur.execute("""
                SELECT * FROM vouchers 
                WHERE platform = ? AND platform_voucher_id = ?
                """, (platform, platform_voucher_id)).fetchone()
                if row:
                    return self._row_to_voucher(dict(row))

            # 2. Trùng platform + code + shop_id
            if voucher_code and voucher_code.strip():
                clean_code = voucher_code.strip().upper()
                if shop_id:
                    row = cur.execute("""
                    SELECT * FROM vouchers 
                    WHERE platform = ? AND UPPER(voucher_code) = ? AND shop_id = ?
                    """, (platform, clean_code, str(shop_id))).fetchone()
                else:
                    row = cur.execute("""
                    SELECT * FROM vouchers 
                    WHERE platform = ? AND UPPER(voucher_code) = ? AND (shop_id IS NULL OR shop_id = '')
                    """, (platform, clean_code)).fetchone()
                if row:
                    return self._row_to_voucher(dict(row))

            # 3. Voucher không code: Trùng claim_url/source_url + discount + min_order + scope/shop_id + start_time
            if claim_url and discount_value:
                query = """
                SELECT * FROM vouchers 
                WHERE platform = ? AND (source_url = ? OR claim_url = ?) 
                  AND discount_value = ? AND min_order_value = ?
                """
                params = [platform, claim_url, claim_url, discount_value, min_order_value]
                if shop_id:
                    query += " AND shop_id = ?"
                    params.append(str(shop_id))
                else:
                    query += " AND (shop_id IS NULL OR shop_id = '')"

                if start_time and str(start_time).strip():
                    query += " AND start_time = ?"
                    params.append(str(start_time).strip())
                else:
                    query += " AND (start_time IS NULL OR start_time = '')"

                row = cur.execute(query, tuple(params)).fetchone()
                if row:
                    return self._row_to_voucher(dict(row))

        return None

    def cleanup_old_records(self) -> Dict[str, int]:
        """Dọn dẹp bản ghi cũ để tối ưu RAM và dung lượng đĩa cho Render Free (512MB):
        - Xóa voucher EXPIRED/CANCELLED quá 7 ngày
        - Giữ tối đa 2.000 observations mới nhất
        - Giữ tối đa 500 source_runs mới nhất
        - Giữ tối đa 1.000 voucher_changes mới nhất
        - Chạy incremental_vacuum / VACUUM
        """
        deleted_counts = {}
        with self.transaction() as cur:
            # 1. Xóa voucher EXPIRED hoặc CANCELLED quá 7 ngày
            cur.execute("""
            DELETE FROM vouchers 
            WHERE status IN ('EXPIRED', 'CANCELLED') 
              AND (
                  (updated_at IS NOT NULL AND updated_at < datetime('now', '-7 days'))
                  OR (end_time IS NOT NULL AND end_time < datetime('now', '-7 days'))
              );
            """)
            deleted_counts["expired_vouchers"] = cur.rowcount

            # 2. Giữ tối đa 2.000 observations mới nhất
            cur.execute("""
            DELETE FROM voucher_observations 
            WHERE id NOT IN (
                SELECT id FROM voucher_observations 
                ORDER BY observed_at DESC 
                LIMIT 2000
            );
            """)
            deleted_counts["pruned_observations"] = cur.rowcount

            # 3. Giữ tối đa 500 source_runs mới nhất
            cur.execute("""
            DELETE FROM source_runs 
            WHERE id NOT IN (
                SELECT id FROM source_runs 
                ORDER BY started_at DESC 
                LIMIT 500
            );
            """)
            deleted_counts["pruned_source_runs"] = cur.rowcount

            # 4. Giữ tối đa 1.000 voucher_changes mới nhất
            cur.execute("""
            DELETE FROM voucher_changes 
            WHERE id NOT IN (
                SELECT id FROM voucher_changes 
                ORDER BY detected_at DESC 
                LIMIT 1000
            );
            """)
            deleted_counts["pruned_changes"] = cur.rowcount

        try:
            conn = self.get_connection()
            conn.isolation_level = None
            conn.execute("PRAGMA incremental_vacuum;")
            conn.close()
        except Exception:
            pass

        return deleted_counts


