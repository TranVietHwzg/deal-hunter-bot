import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Bảng sản phẩm theo dõi (Watchlist)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT DEFAULT 'SHOPEE',
        item_id TEXT UNIQUE,
        shop_id TEXT,
        name TEXT,
        product_url TEXT,
        image_url TEXT,
        target_mode TEXT DEFAULT 'PERCENT',  -- 'PERCENT' hoặc 'PRICE'
        target_value REAL,                    -- ví dụ: 30 (nghĩa là 30%) hoặc 500000 (VND)
        baseline_price REAL,                  -- Giá thị trường chuẩn
        current_price REAL,                   -- Giá niêm yết hiện tại
        final_price REAL,                     -- Giá thực trả sau khi gộp mã
        discount_percent REAL DEFAULT 0,      -- % giảm thực tế
        is_deal_ready INTEGER DEFAULT 0,      -- 1 nếu đạt mục tiêu
        applied_vouchers_json TEXT,           -- Danh sách mã đã gộp
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Bảng lịch sử giá (chống nâng giá ảo)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT,
        price REAL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Bảng kho Voucher (ưu tiên voucher xịn)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id TEXT UNIQUE,
        platform TEXT DEFAULT 'SHOPEE',
        voucher_code TEXT,
        voucher_type TEXT,              -- 'SHOP', 'PLATFORM', 'FREESHIP', 'LIVE_VIDEO'
        discount_type TEXT,             -- 'FIXED' hoặc 'PERCENT'
        discount_val REAL,              -- Ví dụ: 50000 hoặc 15
        max_discount REAL,              -- Mức giảm tối đa
        min_spend REAL,                 -- Đơn tối thiểu
        shop_id TEXT,
        label TEXT,                     -- Tên hiển thị (VD: Giảm 50k đơn từ 300k)
        is_high_tier INTEGER DEFAULT 1, -- 1 nếu là voucher xịn (>=50k hoặc >=15%)
        is_active INTEGER DEFAULT 1,
        expired_at TEXT
    );
    """)

    # 4. Bảng lưu vết cảnh báo đã gửi (chống spam)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts_sent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT,
        final_price REAL,
        discount_percent REAL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

def add_product(item_id, shop_id, name, url, image_url, target_mode, target_value, baseline_price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO products (item_id, shop_id, name, product_url, image_url, target_mode, target_value, baseline_price, current_price, final_price)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(item_id) DO UPDATE SET
        target_mode = excluded.target_mode,
        target_value = excluded.target_value,
        baseline_price = excluded.baseline_price,
        updated_at = CURRENT_TIMESTAMP
    """, (item_id, shop_id, name, url, image_url, target_mode, target_value, baseline_price, baseline_price, baseline_price))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

def get_all_products():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY is_deal_ready DESC, id DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_product_by_id(product_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_product(product_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

def update_product_evaluation(item_id, current_price, final_price, discount_pct, is_ready, vouchers_list):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE products SET
        current_price = ?,
        final_price = ?,
        discount_percent = ?,
        is_deal_ready = ?,
        applied_vouchers_json = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE item_id = ?
    """, (current_price, final_price, discount_pct, 1 if is_ready else 0, json.dumps(vouchers_list, ensure_ascii=False), item_id))
    
    # Lưu vào lịch sử giá
    cursor.execute("INSERT INTO price_history (item_id, price) VALUES (?, ?)", (item_id, current_price))
    conn.commit()
    conn.close()

def get_all_vouchers(only_active=True, only_high_tier=False):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM vouchers WHERE 1=1"
    if only_active:
        query += " AND is_active = 1"
    if only_high_tier:
        query += " AND is_high_tier = 1"
    query += " ORDER BY is_high_tier DESC, discount_val DESC"
    cursor.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def upsert_voucher(v_data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO vouchers (voucher_id, platform, voucher_code, voucher_type, discount_type, discount_val, max_discount, min_spend, shop_id, label, is_high_tier, is_active, expired_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(voucher_id) DO UPDATE SET
        is_active = excluded.is_active,
        discount_val = excluded.discount_val,
        expired_at = excluded.expired_at
    """, (
        v_data["voucher_id"], v_data.get("platform", "SHOPEE"), v_data.get("voucher_code", ""),
        v_data.get("voucher_type", "PLATFORM"), v_data.get("discount_type", "PERCENT"),
        v_data.get("discount_val", 0), v_data.get("max_discount", 0), v_data.get("min_spend", 0),
        v_data.get("shop_id", None), v_data.get("label", ""),
        1 if v_data.get("is_high_tier", True) else 0,
        1 if v_data.get("is_active", True) else 0,
        v_data.get("expired_at", "")
    ))
    conn.commit()
    conn.close()

def should_send_alert(item_id, current_final_price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT final_price FROM alerts_sent WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return True, "DEAL_MOI" # Chưa gửi bao giờ
    last_price = row["final_price"]
    if current_final_price < last_price:
        return True, "GIA_TOT_HON" # Giá rẻ hơn lần gửi trước
    return False, "TRUNG_LAP"

def record_alert_sent(item_id, final_price, discount_pct):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO alerts_sent (item_id, final_price, discount_percent) VALUES (?, ?, ?)", (item_id, final_price, discount_pct))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM products")
    total_products = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as ready FROM products WHERE is_deal_ready = 1")
    ready_deals = cursor.fetchone()["ready"]
    
    cursor.execute("SELECT COUNT(*) as total_v FROM vouchers WHERE is_active = 1")
    active_vouchers = cursor.fetchone()["total_v"]

    cursor.execute("SELECT COUNT(*) as alerts FROM alerts_sent")
    total_alerts = cursor.fetchone()["alerts"]
    
    conn.close()
    return {
        "total_products": total_products,
        "ready_deals": ready_deals,
        "active_vouchers": active_vouchers,
        "total_alerts": total_alerts
    }

# Khởi tạo db khi import
init_db()
