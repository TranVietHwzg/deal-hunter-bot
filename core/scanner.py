import asyncio
from datetime import datetime
from core import database, calculator
from scrapers import shopee

async def seed_default_vouchers():
    """Nạp sẵn các voucher sàn xịn nếu kho voucher đang trống"""
    vouchers = database.get_all_vouchers(only_active=True)
    if not vouchers:
        default_vouchers = shopee.get_default_high_tier_vouchers()
        for v in default_vouchers:
            database.upsert_voucher(v)
        print("[Scanner] Đã nạp sẵn 4 mã voucher sàn & video xịn vào hệ thống.")

async def run_scan_cycle(bot_instance=None):
    """Quét 1 chu kỳ đối soát giá toàn bộ sản phẩm và kho voucher"""
    await seed_default_vouchers()
    products = database.get_all_products()
    vouchers = database.get_all_vouchers(only_active=True)
    
    ready_count = 0
    for p in products:
        try:
            shop_id = p["shop_id"]
            item_id = p["item_id"]
            
            # 1. Cập nhật giá mới nhất
            item_data = await shopee.fetch_shopee_item(shop_id, item_id)
            p["current_price"] = item_data["price"]
            
            # 2. Tính gộp mã
            eval_res = calculator.stack_vouchers_and_evaluate(p, vouchers, min_discount_threshold=30)
            
            # 3. Cập nhật vào SQLite
            database.update_product_evaluation(
                item_id=item_id,
                current_price=eval_res["current_price"],
                final_price=eval_res["final_price"],
                discount_pct=eval_res["discount_percent"],
                is_ready=eval_res["is_deal_ready"],
                vouchers_list=eval_res["applied_vouchers"]
            )
            
            # 4. Kiểm tra điều kiện bắn cảnh báo Telegram
            if eval_res["is_deal_ready"]:
                ready_count += 1
                if bot_instance:
                    should_alert, reason = database.should_send_alert(item_id, eval_res["final_price"])
                    if should_alert:
                        await bot_instance.send_deal_alert(p, eval_res, alert_reason=reason)
                        database.record_alert_sent(item_id, eval_res["final_price"], eval_res["discount_percent"])
                        print(f"[Scanner] Đã bắn cảnh báo deal ngon: {p['name'][:30]} (-{eval_res['discount_percent']}%)")
                        
            # Giãn cách 1-2s giữa các sản phẩm để tránh nghẽn
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"[Scanner] Lỗi quét sản phẩm #{p.get('id')}: {e}")
            
    return ready_count

async def background_scanner_loop(bot_instance, config):
    """
    Vòng lặp quét thích ứng (Adaptive Scheduler):
    - Bình thường: 30s/lần
    - Giờ vàng (0h, 12h): Tự động bật Turbo 2s/lần trong 3 phút
    """
    print("[Scanner] Khởi động luồng quét tự động thích ứng...")
    normal_sleep = config.get("settings", {}).get("normal_interval_seconds", 30)
    turbo_sleep = config.get("settings", {}).get("turbo_interval_seconds", 2)
    
    while True:
        try:
            now = datetime.now()
            # Giờ vàng: 23:59 - 00:03 hoặc 11:59 - 12:03
            is_golden_hour = (
                (now.hour == 23 and now.minute >= 59) or (now.hour == 0 and now.minute <= 3) or
                (now.hour == 11 and now.minute >= 59) or (now.hour == 12 and now.minute <= 3)
            )
            
            await run_scan_cycle(bot_instance)
            
            sleep_duration = turbo_sleep if is_golden_hour else normal_sleep
            await asyncio.sleep(sleep_duration)
        except Exception as e:
            print(f"[Scanner Loop Error]: {e}")
            await asyncio.sleep(10)
