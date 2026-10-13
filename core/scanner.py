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
from services.shopee_live_checker import ShopeeLiveChecker
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
live_checker = ShopeeLiveChecker()

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
            elif itype in ("VOUCHER_EXHAUSTED", "VOUCHER_EXPIRED"):
                if hasattr(bot_instance, "broadcast_voucher_exhausted"):
                    await bot_instance.broadcast_voucher_exhausted(v, itype)

    return scan_res

async def run_lifecycle_step(bot_instance=None):
    """Kiểm tra nhẹ vòng đời và gửi nhắc nhở (tiêu tốn < 1ms, 0 MB RAM)"""
    lifecycle_notifs = lifecycle_service.run_lifecycle_cycle()
    if bot_instance:
        notifier = getattr(bot_instance, "elite_notifier", None)
        for item in lifecycle_notifs:
            itype = item.get("type")
            v = item.get("voucher")
            score = item.get("score", 70)
            if not v:
                continue
            if itype == "VOUCHER_OPENED":
                if notifier:
                    await notifier.notify_elite_voucher(v, "ACTIVE_NOW", score=score)
                else:
                    await bot_instance.broadcast_active_voucher(v)
            elif itype in ("REMINDER_24H", "REMINDER_15M", "REMINDER_2M"):
                await bot_instance.broadcast_reminder(v, itype)
            elif itype in ("VOUCHER_EXHAUSTED", "VOUCHER_EXPIRED"):
                if hasattr(bot_instance, "broadcast_voucher_exhausted"):
                    await bot_instance.broadcast_voucher_exhausted(v, itype)
    return lifecycle_notifs

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
    """Khoảng thời gian nghỉ giữa các lần kiểm tra nhắc giờ"""
    if now is None:
        now = datetime.now(VN_TZ)
    return 5 if is_turbo_active(now) else 15

async def background_radar_loop(bot_instance=None, config=None):
    """
    Vòng lặp chạy nền của Radar tối ưu hóa bộ nhớ cho Render 512MB:
    - Fast loop (5s - 15s): Kiểm tra chính xác giờ mở mã (Lifecycle & Reminder) tốn 0MB RAM.
    - Deep discovery loop (30s - 60s): Quét đa nguồn thu thập deal mới, dọn RAM ngay sau mỗi lượt (gc.collect()).
    - Periodic DB Pruning: Dọn dẹp voucher hết hạn và hạn chế bảng observations.
    """
    import gc
    import time

    print("[Radar Scheduler] Khởi động tiến trình theo dõi mã sắp mở Shopee 24/7 (Memory Safe)...")
    last_deep_scan = 0
    last_live_probe = 0
    last_cleanup = time.time()

    try:
        voucher_repo.cleanup_old_records()
    except Exception as e:
        print(f"[Radar Scheduler] Dọn dẹp DB ban đầu: {e}")

    while True:
        try:
            now_ts = time.time()
            now_dt = datetime.now(VN_TZ)
            turbo = is_turbo_active(now_dt)

            # 1. Luôn chạy kiểm tra vòng đời & nhắc nhở (rất nhẹ, không tốn RAM)
            await run_lifecycle_step(bot_instance)

            # 2. Định kỳ dọn dẹp DB mỗi 6 giờ
            if now_ts - last_cleanup >= 21600:
                last_cleanup = now_ts
                try:
                    voucher_repo.cleanup_old_records()
                except Exception as e:
                    print(f"[Radar Scheduler] Dọn dẹp DB định kỳ: {e}")

            # 3. Chu kỳ cào sâu toàn mạng (Deep Discovery):
            # Trong khung giờ vàng cào 30s/lần; thời gian thường cào 60s/lần
            deep_interval = 30 if turbo else 60
            if now_ts - last_deep_scan >= deep_interval:
                scan_res = await orchestrator.run_discovery_cycle()
                last_deep_scan = now_ts
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

                # Thu gom rác ngay lập tức sau chu kỳ quét sâu để giải phóng RAM về OS
                gc.collect()

            # 4. Chu kỳ Live Status Probe với Shopee API (mỗi 10 - 15 phút):
            # Tự động ping Shopee API để phát hiện và gỡ bỏ mã đã hết lượt
            if now_ts - last_live_probe >= 600:
                last_live_probe = now_ts
                try:
                    active_vouchers = voucher_repo.get_active_vouchers(limit=50)
                    probe_res = await live_checker.probe_active_vouchers(active_vouchers, voucher_repo)
                    if probe_res.get("exhausted_count", 0) > 0:
                        print(f"[Radar Scheduler] Live Probe phát hiện {probe_res['exhausted_count']} mã đã hết lượt!")
                        if bot_instance and hasattr(bot_instance, "broadcast_voucher_exhausted"):
                            for ex_v in probe_res.get("exhausted_vouchers", []):
                                await bot_instance.broadcast_voucher_exhausted(ex_v, "VOUCHER_EXHAUSTED")
                except Exception as probe_err:
                    print(f"[Radar Scheduler] Lỗi Live Probe: {probe_err}")

        except Exception as e:
            print(f"[Radar Scheduler Error] Lỗi chu kỳ quét: {e}")

        sleep_interval = calculate_adaptive_interval()
        await asyncio.sleep(sleep_interval)

# Tương thích ngược
run_scan_cycle = run_radar_cycle
background_scanner_loop = background_radar_loop

