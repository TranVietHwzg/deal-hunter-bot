from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class RestockRadar:
    """
    Module theo dõi vòng đời voucher và phát hiện mã hồi sinh (Restock).
    Trạng thái: UPCOMING -> ACTIVE -> EXHAUSTED -> RESTOCKED -> EXPIRED
    """
    def __init__(self):
        # Lưu cache trạng thái gần nhất: {voucher_id: status}
        self._last_known_status: Dict[str, str] = {}

    def update_and_detect_restock(
        self,
        voucher_id: str,
        new_status: str,
        quality_score: int
    ) -> Optional[Dict[str, Any]]:
        """
        Đối soát trạng thái mới với trạng thái cũ.
        Nếu phát hiện chuyển từ EXHAUSTED sang ACTIVE/RESTOCKED:
        - Báo động khẩn nếu quality_score >= 85.
        """
        old_status = self._last_known_status.get(voucher_id, "ACTIVE")
        self._last_known_status[voucher_id] = new_status

        # Phát hiện hồi sinh
        if old_status in ["EXHAUSTED", "HET_LUOT"] and new_status in ["ACTIVE", "RESTOCKED", "CON_LUOT"]:
            is_urgent = quality_score >= 85
            return {
                "voucher_id": voucher_id,
                "previous_status": old_status,
                "new_status": new_status,
                "quality_score": quality_score,
                "is_urgent_alert": is_urgent,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "reason": f"🔥 MÃ HỒI SINH! Điểm chất lượng: {quality_score}/100" if is_urgent else "Mã đã có lượt trở lại"
            }
        return None

    def is_peak_sale_hour(self) -> bool:
        """
        Kiểm tra xem hiện tại có đang trong khung giờ vàng sale sàn không:
        0h-1h, 9h-10h, 12h-13h, 15h-16h, 18h-19h, 20h-21h
        """
        now_hour = datetime.now().hour
        peak_hours = [0, 9, 12, 15, 18, 20, 21]
        return now_hour in peak_hours
