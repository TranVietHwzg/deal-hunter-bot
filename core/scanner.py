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
from services.lifecycle_service import LifecycleService
from models.scan_run import ScanMode
from core.voucher_lifecycle import parse_vietnam_time, VN_TZ

voucher_repo = VoucherRepository()
shop_repo = ShopRepository()
scan_repo = ScanRepository()
discovery_service = DiscoveryService(voucher_repo, scan_repo)
lifecycle_service = LifecycleService(voucher_repo, scan_repo)

async def seed_default_vouchers():
    """Đồng bộ ban đầu kho voucher Shopee chiến dịch & mã ẩn"""
    await discovery_service.run_scan(ScanMode.AUTO)
    print("[Radar] Đã nạp thành công kho mã Shopee ban đầu (ZERO FREESHIP).")

async def run_radar_cycle(bot_instance=None) -> Dict[str, Any]:
    """Chạy một chu kỳ Radar hoàn chỉnh (Discovery + Lifecycle check)"""
    # 1. Quét khám phá nguồn Shopee công khai
    scan_res = await discovery_service.run_scan(ScanMode.AUTO)

    # 2. Gửi thông báo cho các voucher mới phát hiện
    if bot_instance:
        for ev in scan_res.get("events_to_notify", []):
            ev_type = ev.get("type")
            v = ev.get("voucher")
            if not v:
                continue
            if ev_type in ("UPCOMING_KNOWN", "UPCOMING_UNKNOWN"):
                await bot_instance.broadcast_upcoming_voucher(v)
            elif ev_type == "ACTIVE_NEW":
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

def calculate_adaptive_interval() -> int:
    """
    Tính toán khoảng thời gian ngủ thích ứng (Adaptive Interval):
    - Có mã sắp mở trong < 5 phút: quét mỗi 30s (chống miss mã 0đ)
    - Có mã sắp mở trong < 30 phút: quét mỗi 5 phút (300s)
    - Có mã sắp mở trong < 24 giờ: quét mỗi 15 phút (900s)
    - Bình thường: quét mỗi 60 phút (3600s)
    """
    upcoming = voucher_repo.get_upcoming_vouchers(days=1)
    if not upcoming:
        return 3600

    now = datetime.now(VN_TZ)
    min_diff = None
    for v in upcoming:
        dt = parse_vietnam_time(v.start_time)
        if dt and dt > now:
            diff = (dt - now).total_seconds()
            if min_diff is None or diff < min_diff:
                min_diff = diff

    if min_diff is not None:
        if min_diff <= 5 * 60:
            return 30  # 30 giây, chống miss mã 100k/0đ
        if min_diff <= 30 * 60:
            return 300  # 5 phút
        elif min_diff <= 24 * 3600:
            return 900  # 15 phút

    return 3600

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

