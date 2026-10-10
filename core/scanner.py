import asyncio
import hashlib
from datetime import datetime
from core import database, calculator
from scrapers import shopee, voucher_hunter
from app.connectors.shopee_connector import ShopeeConnector
from app.core.restock_radar import RestockRadar

shopee_conn = ShopeeConnector()
restock_radar = RestockRadar()

async def seed_default_vouchers():
    """Nạp và đồng bộ kho voucher Shopee chất lượng cao (Bài trừ 100% Freeship)"""
    # 1. Từ danh mục chuẩn
    catalog = voucher_hunter.get_comprehensive_voucher_catalog()
    for v in catalog:
        database.upsert_voucher(v)

    # 2. Từ Shopee Connector
    await shopee_conn.fetch_vouchers()
    print(f"[Scanner] Đã đồng bộ kho voucher Shopee sạch (ZERO FREESHIP) thành công.")

async def run_scan_cycle(bot_instance=None):
    """Quét 1 chu kỳ đối soát giá toàn bộ sản phẩm và kho voucher"""
    await seed_default_vouchers()
    products = database.get_all_products()
    vouchers = database.get_vouchers(min_score=60)
    
    ready_count = 0
    for p in products:
        try:
            shop_id = p.get("shop_id")
            item_id = p.get("item_id") or p.get("item_id_on_platform")
            
            # 1. Cập nhật giá mới nhất
            item_data = await shopee.fetch_shopee_item(shop_id, item_id)
            current_price = item_data.get("price", p.get("current_price", 0))
            p["current_price"] = current_price
            
            # 2. Tính gộp mã qua Stacking Engine chuẩn (Không freeship)
            eval_res = calculator.stack_vouchers_and_evaluate(p, vouchers, min_discount_threshold=15)
            
            # 3. Cập nhật vào SQLite
            database.update_product_evaluation(
                item_id=item_id,
                current_price=eval_res["current_price"],
                final_price=eval_res["final_price"],
                discount_percent=eval_res["discount_percent"],
                is_deal_ready=1 if eval_res["is_deal_ready"] else 0,
                applied_vouchers=eval_res["applied_vouchers"]
            )
            
            # 4. Kiểm tra điều kiện bắn cảnh báo Telegram
            if eval_res["is_deal_ready"]:
                ready_count += 1
                if bot_instance:
                    # Tạo SHA-256 dedup hash
                    raw_hash = f"DEAL_{item_id}_{int(eval_res['final_price'])}_{eval_res['discount_percent']}"
                    dedup_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
                    
                    if not database.is_alert_duplicate(dedup_hash):
                        await bot_instance.send_deal_alert(p, eval_res, alert_reason="DEAL_MOI")
                        database.record_alert_event(
                            alert_type="TARGET_MET",
                            dedup_hash=dedup_hash,
                            message_payload=f"Deal {p['name']}",
                            product_id=item_id,
                            final_price=eval_res["final_price"]
                        )
                        print(f"[Scanner] Đã gửi cảnh báo deal chuẩn: {p['name'][:30]} (-{eval_res['discount_percent']}%)")
                        
            await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[Scanner] Lỗi quét sản phẩm #{p.get('id')}: {e}")
            
    return ready_count

async def background_scanner_loop(bot_instance, config):
    """
    Vòng lặp quét tự động thích ứng (Adaptive Scheduler):
    - Bình thường: 30s/lần
    - Khung giờ vàng sale (0h, 9h, 12h, 21h): Tăng tần suất quét
    """
    print("[Scanner] Khởi động luồng quét tự động thích ứng...")
    normal_sleep = config.get("settings", {}).get("normal_interval_seconds", 30)
    turbo_sleep = config.get("settings", {}).get("turbo_interval_seconds", 5)
    
    while True:
        try:
            is_peak = restock_radar.is_peak_sale_hour()
            await run_scan_cycle(bot_instance)
            sleep_duration = turbo_sleep if is_peak else normal_sleep
            await asyncio.sleep(sleep_duration)
        except Exception as e:
            print(f"[Scanner Loop Error]: {e}")
            await asyncio.sleep(10)
