import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core import database, calculator
from scrapers import shopee

app = FastAPI(title="Deal Hunter Dashboard")

class AddProductPayload(BaseModel):
    url: str
    target_mode: str = "PERCENT"  # "PERCENT" hoặc "PRICE"
    target_value: float = 30.0

@app.get("/api/stats")
def api_get_stats():
    return database.get_stats()

@app.get("/api/products")
def api_get_products():
    products = database.get_all_products()
    for p in products:
        if p.get("applied_vouchers_json"):
            try:
                p["applied_vouchers"] = json.loads(p["applied_vouchers_json"])
            except Exception:
                p["applied_vouchers"] = []
        else:
            p["applied_vouchers"] = []
    return products

@app.post("/api/products")
async def api_add_product(payload: AddProductPayload):
    real_url = await shopee.resolve_short_url(payload.url)
    shop_id, item_id = shopee.parse_shopee_url(real_url)
    if not item_id:
        return {"ok": False, "error": "Không thể trích xuất mã sản phẩm từ link Shopee!"}
        
    item_data = await shopee.fetch_shopee_item(shop_id, item_id)
    p_id = database.add_product(
        item_id=item_id,
        shop_id=shop_id,
        name=item_data["name"],
        url=real_url,
        image_url=item_data["image_url"],
        target_mode=payload.target_mode,
        target_value=payload.target_value,
        baseline_price=item_data["baseline_price"]
    )
    
    # Đánh giá ngay
    vouchers = database.get_all_vouchers()
    p_obj = database.get_product_by_id(p_id)
    eval_res = calculator.stack_vouchers_and_evaluate(p_obj, vouchers)
    database.update_product_evaluation(item_id, eval_res["current_price"], eval_res["final_price"], eval_res["discount_percent"], eval_res["is_deal_ready"], eval_res["applied_vouchers"])
    
    return {"ok": True, "product_id": p_id, "name": item_data["name"], "eval": eval_res}

@app.delete("/api/products/{product_id}")
def api_delete_product(product_id: int):
    database.delete_product(product_id)
    return {"ok": True}

@app.get("/api/vouchers")
def api_get_vouchers():
    return database.get_all_vouchers(only_active=True)

@app.post("/api/scan-now")
async def api_scan_now():
    from core.scanner import run_scan_cycle
    count = await run_scan_cycle(None)
    return {"ok": True, "ready_count": count}

@app.get("/", response_class=HTMLResponse)
def get_dashboard_html():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Dashboard template not found</h1>"
