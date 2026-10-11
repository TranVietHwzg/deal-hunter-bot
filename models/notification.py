from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class NotificationEventType(str, Enum):
    NEW_CODE = "NEW_CODE"
    EVENT_UPCOMING = "EVENT_UPCOMING"
    CODE_REVEALED = "CODE_REVEALED"
    VOUCHER_OPENED = "VOUCHER_OPENED"
    TIME_CHANGED = "TIME_CHANGED"
    VALUE_CHANGED = "VALUE_CHANGED"
    REMINDER_60M = "REMINDER_60M"
    REMINDER_24H = "REMINDER_24H"
    REMINDER_15M = "REMINDER_15M"
    REMINDER_5M = "REMINDER_5M"
    REMINDER_2M = "REMINDER_2M"
    VOUCHER_RESTOCKED = "VOUCHER_RESTOCKED"

@dataclass
class NotificationEvent:
    id: str
    voucher_id: str
    event_type: NotificationEventType
    content_fingerprint: str
    sent_at: Optional[str] = None
    telegram_message_id: Optional[int] = None
    delivery_status: str = "SENT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "voucher_id": self.voucher_id,
            "event_type": self.event_type.value if isinstance(self.event_type, NotificationEventType) else self.event_type,
            "content_fingerprint": self.content_fingerprint,
            "sent_at": self.sent_at,
            "telegram_message_id": self.telegram_message_id,
            "delivery_status": self.delivery_status
        }
