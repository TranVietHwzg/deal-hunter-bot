from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from repositories.base_repository import BaseRepository
from models.scan_run import ScanRun, ScanMode
from models.notification import NotificationEvent, NotificationEventType

class ScanRepository(BaseRepository):
    def init_schema(self) -> None:
        with self.transaction() as cur:
            # 1. Bảng notification_events
            cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_events (
                id TEXT PRIMARY KEY,
                voucher_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                telegram_message_id INTEGER,
                content_fingerprint TEXT NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'SENT',
                FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_fingerprint ON notification_events(content_fingerprint);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_voucher_event ON notification_events(voucher_id, event_type);")

            # 2. Bảng scan_runs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                scan_id TEXT PRIMARY KEY,
                scan_mode TEXT NOT NULL,
                source_or_module TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                items_scanned INTEGER DEFAULT 0,
                new_vouchers INTEGER DEFAULT 0,
                updated_vouchers INTEGER DEFAULT 0,
                errors TEXT,
                rate_limit_state TEXT DEFAULT 'NORMAL'
            );
            """)

    def start_scan_run(self, scan_id: str, scan_mode: ScanMode, source_or_module: str) -> None:
        with self.transaction() as cur:
            cur.execute("""
            INSERT INTO scan_runs (scan_id, scan_mode, source_or_module, started_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                scan_id,
                scan_mode.value if isinstance(scan_mode, ScanMode) else scan_mode,
                source_or_module
            ))

    def finish_scan_run(
        self,
        scan_id: str,
        items_scanned: int,
        new_vouchers: int,
        updated_vouchers: int,
        errors: Optional[str] = None,
        rate_limit_state: str = "NORMAL"
    ) -> None:
        with self.transaction() as cur:
            cur.execute("""
            UPDATE scan_runs SET
                finished_at = CURRENT_TIMESTAMP,
                items_scanned = ?,
                new_vouchers = ?,
                updated_vouchers = ?,
                errors = ?,
                rate_limit_state = ?
            WHERE scan_id = ?
            """, (items_scanned, new_vouchers, updated_vouchers, errors, rate_limit_state, scan_id))

    def record_notification(self, event: NotificationEvent) -> None:
        with self.transaction() as cur:
            cur.execute("""
            INSERT OR REPLACE INTO notification_events (
                id, voucher_id, event_type, content_fingerprint, telegram_message_id, delivery_status, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                event.id,
                event.voucher_id,
                event.event_type.value if isinstance(event.event_type, NotificationEventType) else event.event_type,
                event.content_fingerprint,
                event.telegram_message_id,
                event.delivery_status
            ))

    def is_notification_duplicate(self, fingerprint: str) -> bool:
        with self.transaction() as cur:
            row = cur.execute(
                "SELECT 1 FROM notification_events WHERE content_fingerprint = ? LIMIT 1",
                (fingerprint,)
            ).fetchone()
            return row is not None

    def get_latest_scan_run(self) -> Optional[Dict[str, Any]]:
        with self.transaction() as cur:
            row = cur.execute("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            if row:
                return dict(row)
        return None
