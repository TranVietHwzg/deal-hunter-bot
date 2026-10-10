import hashlib
import pytest
from core.database import init_db, record_alert_event, is_alert_duplicate

def generate_dedup_hash(item_id: str, voucher_ids: list, final_price: float) -> str:
    raw = f"{item_id}_{sorted(voucher_ids)}_{int(final_price)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def test_alert_deduplication():
    init_db()
    import uuid
    item_id = f"test_item_{uuid.uuid4()}"
    voucher_ids = ["V1", "V2"]
    final_price = 450000.0
    dedup_hash = generate_dedup_hash(item_id, voucher_ids, final_price)

    # Lần 1: Gửi thành công
    success_1 = record_alert_event(
        alert_type="HOT_VOUCHER",
        dedup_hash=dedup_hash,
        message_payload="Test Alert Message 1",
        final_price=final_price
    )
    assert success_1 is True
    assert is_alert_duplicate(dedup_hash) is True

    # Lần 2: Bắn lại đúng event đó -> Hệ thống phải chặn đứng (Trả về False)
    success_2 = record_alert_event(
        alert_type="HOT_VOUCHER",
        dedup_hash=dedup_hash,
        message_payload="Test Alert Message 2",
        final_price=final_price
    )
    assert success_2 is False, "Duplicate alert must be blocked by database unique dedup_hash constraint"
