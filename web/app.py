import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core import database, calculator
from scrapers import shopee
from app.connectors.shopee_connector import ShopeeConnector

app = FastAPI(
    title="Voucher Intelligence & Deal Optimizer API",
    description="Hệ thống cá nhân tối ưu voucher đa sàn TMĐT, loại trừ 100% Freeship, tính giá thực trả gộp mã",
    version="2.0.0"
)

shopee_connector = ShopeeConnector()

class AddProductPayload(BaseModel):
    url: str
    target_mode: str = "PERCENT"
    target_value: float = 30.0

@app.get("/health")
def healthcheck():
    """Endpoint kiểm tra trạng thái sức khỏe của toàn hệ thống"""
    return {
        "status": "healthy",
        "service": "voucher-intelligence-optimizer",
        "zero_freeship_policy": "ENFORCED",
        "version": "2.0.0"
    }

@app.get("/metrics")
def get_metrics():
    """Thống kê vận hành cho giám sát Prometheus / Grafana"""
    vouchers = database.get_vouchers(min_score=0)
    products = database.get_all_products()
    hot_count = len([v for v in vouchers if v.get("is_hot") == 1])
    ready_count = len([p for p in products if p.get("is_deal_ready") == 1])
    
    return {
        "total_active_vouchers": len(vouchers),
        "hot_vouchers_count": hot_count,
        "tracked_products_count": len(products),
        "ready_deals_count": ready_count,
        "circuit_breaker_shopee": shopee_connector.circuit_breaker.state
    }

@app.get("/api/stats")
def api_get_stats():
    vouchers = database.get_vouchers(min_score=0)
    products = database.get_all_products()
    return {
        "total_products": len(products),
        "ready_deals": len([p for p in products if p.get("is_deal_ready") == 1]),
        "total_vouchers": len(vouchers),
        "hot_vouchers": len([v for v in vouchers if v.get("quality_score", 0) >= 85])
    }

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
    parsed = await shopee_connector.resolve_url_and_parse(payload.url)
    shop_id, item_id = parsed.get("shop_id"), parsed.get("item_id")
    if not item_id:
        return {"ok": False, "error": "Không thể trích xuất mã sản phẩm từ link Shopee!"}

    details = await shopee_connector.fetch_product_details(
        item_id,
        shop_id,
        name_hint=parsed.get("name"),
        image_hint=parsed.get("image_url")
    )
    database.add_product(
        item_id=item_id,
        shop_id=shop_id,
        name=details["name"],
        url=payload.url,
        image_url=details.get("image_url"),
        target_mode=payload.target_mode,
        target_value=payload.target_value,
        baseline_price=details["original_price"]
    )

    vouchers = database.get_vouchers(min_score=60)
    p_obj = database.get_product_by_id(item_id)
    eval_res = calculator.stack_vouchers_and_evaluate(p_obj, vouchers)
    database.update_product_evaluation(
        item_id=item_id,
        current_price=eval_res["current_price"],
        final_price=eval_res["final_price"],
        discount_percent=eval_res["discount_percent"],
        is_deal_ready=1 if eval_res["is_deal_ready"] else 0,
        applied_vouchers=eval_res["applied_vouchers"]
    )

    return {"ok": True, "item_id": item_id, "name": details["name"], "eval": eval_res}

@app.delete("/api/products/{item_id}")
def api_delete_product(item_id: str):
    database.delete_product(item_id)
    return {"ok": True}

@app.get("/api/vouchers")
def api_get_vouchers(min_score: int = 70):
    return database.get_vouchers(min_score=min_score)

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
    return "<h1>Voucher Intelligence & Deal Optimizer Dashboard</h1><p>Hệ thống hoạt động bình thường.</p>"
