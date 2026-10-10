import asyncio
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
from core import database, calculator, scanner
from scrapers import shopee

def run_tests():
    print("--- 1. KIỂM TRA DATABASE ---")
    database.init_db()
    stats = database.get_stats()
    print("Thống kê hiện tại:", stats)

    print("\n--- 2. KIỂM TRA BỘ TÍNH GỘP MÃ (CALCULATOR) ---")
    mock_product = {
        "baseline_price": 650000,
        "current_price": 650000,
        "shop_id": "88888",
        "target_mode": "PERCENT",
        "target_value": 40.0
    }
    mock_vouchers = shopee.get_default_high_tier_vouchers()
    res = calculator.stack_vouchers_and_evaluate(mock_product, mock_vouchers)
    print(f"Ket qua Deal 30.4% voi muc tieu 40%: Dat muc tieu = {res['is_deal_ready']}")
    assert res["is_deal_ready"] == False, "Deal 30.4% voi muc tieu 40% phai bi tu choi!"
    print(" Da kiem chung: Deal chua dat muc tieu bi tu choi chinh xac.")

    # Thử nghiệm Deal đạt chuẩn >= 40%
    mock_vouchers_with_shop = mock_vouchers + [{
        "voucher_id": "SHOP_VOUCHER_120K",
        "voucher_code": "SHOP120K",
        "voucher_type": "SHOP",
        "discount_type": "FIXED",
        "discount_val": 120000,
        "max_discount": 120000,
        "min_spend": 500000,
        "shop_id": "88888",
        "label": "Mã Shop: Giảm 120k",
        "is_active": 1
    }]
    res2 = calculator.stack_vouchers_and_evaluate(mock_product, mock_vouchers_with_shop)
    print(f"Deal co ma Shop: Gia thuc tra = {int(res2['final_price']):,}d, Giam that = {res2['discount_percent']}%, Dat muc tieu = {res2['is_deal_ready']}")
    assert res2["is_deal_ready"] == True, "Deal >= 40% phai duoc chap nhan!"
    print(" Da kiem chung: Deal dat muc tieu duoc duyet chinh xac.")
    print("\n✅ TẤT CẢ LOGIC BỘ LỌC ĐẠT CHUẨN 100%!")

if __name__ == "__main__":
    run_tests()
