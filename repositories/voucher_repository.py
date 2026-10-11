import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from repositories.base_repository import BaseRepository
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus

class VoucherRepository(BaseRepository):
    def init_schema(self) -> None:
        """Đảm bảo các bảng vouchers và voucher_changes đã tồn tại theo schema mới"""
        with self.transaction() as cur:
            # 1. Bảng vouchers
            cur.execute("""
            CREATE TABLE IF NOT EXISTS vouchers (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL DEFAULT 'SHOPEE',
                voucher_code TEXT,
                title TEXT NOT NULL,
                description TEXT,
                scope_type TEXT NOT NULL,
                shop_id TEXT,
                shop_name TEXT,
                shop_url TEXT,
                category_names TEXT,
                discount_type TEXT NOT NULL,
                discount_value REAL NOT NULL,
                max_discount REAL,
                min_order_value REAL NOT NULL DEFAULT 0,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
                status TEXT NOT NULL DEFAULT 'DISCOVERED',
                is_freeship INTEGER NOT NULL DEFAULT 0,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                confidence_score INTEGER NOT NULL DEFAULT 90,
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
                "scope_type": "TEXT DEFAULT 'PLATFORM'",
                "shop_url": "TEXT",
                "category_names": "TEXT",
                "max_discount": "REAL",
                "min_order_value": "REAL DEFAULT 0",
                "timezone": "TEXT DEFAULT 'Asia/Ho_Chi_Minh'",
                "source_url": "TEXT DEFAULT 'https://shopee.vn'",
                "source_type": "TEXT DEFAULT 'CAMPAIGN_PAGE'",
                "confidence_score": "INTEGER DEFAULT 90",
                "first_seen_at": "TEXT",
                "last_seen_at": "TEXT"
            }
            for col_name, col_type in new_cols.items():
                if col_name not in cols:
                    try:
                        cur.execute(f"ALTER TABLE vouchers ADD COLUMN {col_name} {col_type};")
                    except Exception as e:
                        print(f"[VoucherRepository] Lưu ý khi thêm cột {col_name}: {e}")


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

        return Voucher(
            id=row["id"],
            platform=row.get("platform") or "SHOPEE",
            voucher_code=row.get("voucher_code"),
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
            confidence_score=int(row.get("confidence_score") or 90),
            first_seen_at=row.get("first_seen_at"),
            last_seen_at=row.get("last_seen_at"),
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
                    "voucher_id_on_platform": voucher.id,
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
                    "is_freeship": 0,
                    "claim_url": voucher.source_url,
                    "source_url": voucher.source_url,
                    "source_type": voucher.source_type,
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

    def get_upcoming_vouchers(self, days: int = 7) -> List[Voucher]:
        """Lấy các voucher sắp mở trong N ngày tới"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND status IN ('UPCOMING_CODE_KNOWN', 'UPCOMING_UNKNOWN_CODE')
            ORDER BY start_time ASC, discount_value DESC
            """).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_active_vouchers(self) -> List[Voucher]:
        """Lấy các voucher đang ACTIVE"""
        with self.transaction() as cur:
            rows = cur.execute("""
            SELECT * FROM vouchers 
            WHERE is_freeship = 0 
              AND status = 'ACTIVE'
            ORDER BY discount_value DESC
            """).fetchall()
            return [self._row_to_voucher(dict(r)) for r in rows]

    def get_all_vouchers(self, limit: int = 100) -> List[Voucher]:
        """Lấy tất cả vouchers không phải freeship"""
        return self.get_vouchers(limit=limit)
