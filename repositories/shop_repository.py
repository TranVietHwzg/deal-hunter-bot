from typing import List, Optional, Dict, Any
from repositories.base_repository import BaseRepository
from models.tracked_shop import TrackedShop

class ShopRepository(BaseRepository):
    def init_schema(self) -> None:
        with self.transaction() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS tracked_shops (
                shop_id TEXT PRIMARY KEY,
                shop_name TEXT NOT NULL,
                shop_url TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_scan_at TIMESTAMP
            );
            """)

    def add_shop(self, shop_id: str, shop_name: str, shop_url: str) -> bool:
        with self.transaction() as cur:
            cur.execute("""
            INSERT INTO tracked_shops (shop_id, shop_name, shop_url, enabled, added_at)
            VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(shop_id) DO UPDATE SET
                shop_name = excluded.shop_name,
                shop_url = excluded.shop_url,
                enabled = 1
            """, (shop_id, shop_name, shop_url))
            return True

    def remove_shop(self, identifier: str) -> bool:
        """Xóa theo shop_id hoặc shop_url hoặc shop_name"""
        with self.transaction() as cur:
            res = cur.execute("""
            DELETE FROM tracked_shops 
            WHERE shop_id = ? OR shop_url = ? OR shop_name = ?
            """, (identifier, identifier, identifier))
            return res.rowcount > 0

    def get_tracked_shops(self, enabled_only: bool = True) -> List[TrackedShop]:
        sql = "SELECT * FROM tracked_shops"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY added_at DESC"

        with self.transaction() as cur:
            rows = cur.execute(sql).fetchall()
            return [
                TrackedShop(
                    shop_id=r["shop_id"],
                    shop_name=r["shop_name"],
                    shop_url=r["shop_url"],
                    enabled=r["enabled"],
                    added_at=r["added_at"],
                    last_scan_at=r["last_scan_at"]
                )
                for r in rows
            ]

    def update_last_scan(self, shop_id: str) -> None:
        with self.transaction() as cur:
            cur.execute("""
            UPDATE tracked_shops SET last_scan_at = CURRENT_TIMESTAMP WHERE shop_id = ?
            """, (shop_id,))
