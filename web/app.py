import asyncio
import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from core import database, calculator
from app.connectors.shopee_connector import ShopeeConnector

app = FastAPI(
    title="Shopee Upcoming Hidden Voucher Radar API",
    description="Hệ thống cá nhân theo dõi voucher Shopee sắp mở, mã ẩn công khai, loại trừ 100% Freeship",
    version="2.0.0"
)

shopee_connector = ShopeeConnector()

class AddProductPayload(BaseModel):
    url: str
    target_mode: str = "PERCENT"
    target_value: float = 30.0

@app.get("/health")
def healthcheck():
    """Endpoint kiểm tra trạng thái sức khỏe của hệ thống cho Render"""
    return {
        "status": "healthy",
        "service": "shopee-upcoming-hidden-voucher-radar",
        "zero_freeship_policy": "ENFORCED",
        "version": "2.0.0"
    }

@app.get("/metrics")
def get_metrics():
    """Thống kê vận hành cho giám sát Prometheus / Grafana"""
    vouchers = database.get_vouchers(min_score=0)
    products = database.get_all_products()
    hot_count = len([v for v in vouchers if v.get("is_hot") == 1])
    
    return {
        "total_active_vouchers": len(vouchers),
        "hot_vouchers_count": hot_count,
        "tracked_products_count": len(products),
        "circuit_breaker_shopee": shopee_connector.circuit_breaker.state
    }

@app.get("/api/stats")
def api_get_stats():
    vouchers = database.get_vouchers(min_score=0)
    return {
        "total_vouchers": len(vouchers),
        "hot_vouchers": len([v for v in vouchers if v.get("discount_value", 0) >= 50000])
    }

@app.get("/api/vouchers")
def api_get_vouchers(min_score: int = 70):
    return database.get_vouchers(min_score=min_score)

@app.post("/api/scan-now")
async def api_scan_now():
    from core.scanner import run_radar_cycle
    res = await run_radar_cycle(None)
    return {"ok": True, "result": res}

@app.get("/", response_class=HTMLResponse)
def get_dashboard_html():
    return """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Shopee Upcoming Hidden Voucher Radar</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background: #0f172a;
                color: #f8fafc;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 1rem;
                box-sizing: border-box;
            }
            .card {
                background: #1e293b;
                padding: 2.5rem;
                border-radius: 1.25rem;
                border: 1px solid #334155;
                text-align: center;
                max-width: 520px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            }
            .icon { font-size: 3rem; margin-bottom: 0.5rem; }
            h1 { color: #38bdf8; font-size: 1.6rem; margin-bottom: 0.75rem; }
            p { color: #94a3b8; font-size: 0.95rem; line-height: 1.6; margin-bottom: 1.5rem; }
            .badge-group { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 1.5rem; }
            .badge {
                background: #0369a1;
                color: #e0f2fe;
                padding: 0.35rem 0.85rem;
                border-radius: 9999px;
                font-weight: 600;
                font-size: 0.8rem;
            }
            .badge.success { background: #15803d; color: #dcfce7; }
            .telegram-btn {
                display: inline-block;
                background: #2563eb;
                color: white;
                text-decoration: none;
                font-weight: 600;
                padding: 0.75rem 1.5rem;
                border-radius: 0.75rem;
                transition: background 0.2s;
            }
            .telegram-btn:hover { background: #1d4ed8; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">📡</div>
            <h1>Shopee Voucher Radar</h1>
            <p>Hệ thống tự động phát hiện mã sắp mở, mã ẩn công khai và voucher gian hàng Shopee đang chạy 24/7.</p>
            <div class="badge-group">
                <span class="badge success">🟢 ONLINE & HEALTHY</span>
                <span class="badge">🚫 ZERO FREESHIP</span>
                <span class="badge">⏰ ASIA/HO_CHI_MINH</span>
            </div>
            <div>
                <a class="telegram-btn" href="https://t.me/San_deal_Huvg_bot" target="_blank">🤖 Mở Telegram Bot</a>
            </div>
        </div>
    </body>
    </html>
    """
