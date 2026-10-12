import asyncio
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository
from services.discovery_service import DiscoveryService
from services.elite_discovery_service import EliteDiscoveryService
from services.lifecycle_service import LifecycleService
from core.discovery_orchestrator import DiscoveryOrchestrator
from models.scan_run import ScanMode
from core.voucher_lifecycle import parse_vietnam_time, VN_TZ

voucher_repo = VoucherRepository()
shop_repo = ShopRepository()
scan_repo = ScanRepository()
discovery_service = DiscoveryService(voucher_repo, scan_repo)
elite_discovery = EliteDiscoveryService(voucher_repo, scan_repo, shop_repo)
orchestrator = DiscoveryOrchestrator(voucher_repo, shop_repo, scan_repo)
lifecycle_service = LifecycleService(voucher_repo, scan_repo)

async def seed_default_vouchers():
    """Đồng bộ ban đầu kho voucher Shopee qua Discovery Orchestrator"""
    await orchestrator.run_discovery_cycle()
    print("[Radar] Đã nạp thành công kho quan sát ban đầu qua Discovery Orchestrator.")

async def run_radar_cycle(bot_instance=None) -> Dict[str, Any]:
    """Chạy một chu kỳ Radar hoàn chỉnh (Discovery Orchestrator + Lifecycle check)"""
    # 1. Thu thập đa nguồn và đánh giá độc lập qua Discovery Orchestrator
    scan_res = await orchestrator.run_discovery_cycle()

    # 2. Gửi thông báo cho các sự kiện mới phát hiện
    if bot_instance:
        notifier = getattr(bot_instance, "elite_notifier", None)
        for ev in scan_res.get("events_to_notify", []):
            ev_type = ev.get("type")
            v = ev.get("voucher")
            if not v:
                continue
            mapped_type = {
                "READY_NOW": "ACTIVE_NEW",
                "UPCOMING": "UPCOMING_KNOWN",
                "WATCH": "UPCOMING_UNKNOWN",
                "CODE_REVEALED": "CODE_REVEALED"
            }.get(ev_type, ev_type)

            if notifier:
                await notifier.notify_elite_voucher(v, mapped_type, score=v.confidence_score)
            else:
                if ev_type in ("UPCOMING", "WATCH"):
                    await bot_instance.broadcast_upcoming_voucher(v)
                elif ev_type == "READY_NOW":
                    await bot_instance.broadcast_active_voucher(v)
                elif ev_type == "CODE_REVEALED":
                    await bot_instance.broadcast_code_revealed(v)

    # 3. Chạy Lifecycle Check (chuyển ACTIVE, nhắc giờ T-15m / T-2m)
    lifecycle_notifs = lifecycle_service.run_lifecycle_cycle()
    if bot_instance:
        for item in lifecycle_notifs:
            itype = item.get("type")
            v = item.get("voucher")
            if not v:
                continue
            if itype == "VOUCHER_OPENED":
                await bot_instance.broadcast_active_voucher(v)
            elif itype in ("REMINDER_15M", "REMINDER_2M"):
                await bot_instance.broadcast_reminder(v, itype)

    return scan_res

GOLD_HOURS = [0, 12, 20]

def is_turbo_active(now: Optional[datetime] = None) -> bool:
    """
    Kiểm tra xem hiện tại có đang trong khung thời gian Turbo (2s) không:
    - 15 phút trước và 5 phút sau các khung giờ vàng Shopee: 0H, 12H, 20H.
    - 15 phút trước và 5 phút sau giờ mở của bất kỳ voucher UPCOMING nào trong hệ thống.
    """
    if now is None:
        now = datetime.now(VN_TZ)

    # 1. Cự ly tới các khung giờ vàng
    for gh in GOLD_HOURS:
        target_today = datetime(now.year, now.month, now.day, gh, 0, tzinfo=VN_TZ)
        diff_secs = (target_today - now).total_seconds()
        if -300 <= diff_secs <= 900:
            return True
        # Xét thêm 0h ngày mai nếu hiện tại là 23h45 - 23h59
        if gh == 0 and now.hour == 23:
            target_next = target_today + timedelta(days=1)
            diff_next = (target_next - now).total_seconds()
            if -300 <= diff_next <= 900:
                return True

    # 2. Cự ly tới giờ mở của các voucher sắp mở
    try:
        upcoming = voucher_repo.get_upcoming_vouchers(days=1)
        for v in upcoming:
            dt = parse_vietnam_time(v.start_time)
            if dt:
                diff = (dt - now).total_seconds()
                if -300 <= diff <= 900:
                    return True
    except Exception:
        pass

    return False

def calculate_adaptive_interval(now: Optional[datetime] = None) -> int:
    """
    Tính toán khoảng thời gian ngủ thích ứng (Adaptive Interval):
    - Chế độ TURBO (2s): 15 phút trước khung giờ vàng (0H, 12H, 20H) hoặc trước giờ mở mã.
    - Chế độ NORMAL (30s): Các khoảng thời gian còn lại.
    """
    if now is None:
        now = datetime.now(VN_TZ)

    if is_turbo_active(now):
        return 2  # Turbo mode: 2 giây

    return 30  # Normal mode: 30 giây

async def background_radar_loop(bot_instance=None, config=None):
    """Vòng lặp chạy nền của Radar với tần suất thích ứng"""
    print("[Radar Scheduler] Khởi động tiến trình theo dõi mã sắp mở Shopee 24/7...")
    while True:
        try:
            await run_radar_cycle(bot_instance)
        except Exception as e:
            print(f"[Radar Scheduler Error] Lỗi chu kỳ quét: {e}")

        interval = calculate_adaptive_interval()
        await asyncio.sleep(interval)

# Tương thích ngược
run_scan_cycle = run_radar_cycle
background_scanner_loop = background_radar_loop

