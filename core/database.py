import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Bảng Platforms
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS platforms (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        base_url TEXT NOT NULL,
        is_enabled INTEGER NOT NULL DEFAULT 1,
        rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Kiểm tra xem bảng vouchers cũ có cần migrate không
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vouchers'")
    if cursor.fetchone():
        cols = [c[1] for c in cursor.execute("PRAGMA table_info(vouchers)").fetchall()]
        if "title" not in cols:
            # Backup & recreate
            cursor.execute("ALTER TABLE vouchers RENAME TO old_vouchers")
            cursor.execute("""
            CREATE TABLE vouchers (
                id TEXT PRIMARY KEY,
                platform_id TEXT NOT NULL DEFAULT 'SHOPEE',
                voucher_id_on_platform TEXT NOT NULL,
                voucher_code TEXT,
                voucher_type TEXT NOT NULL,
                category TEXT,
                title TEXT NOT NULL,
                description TEXT,
                discount_type TEXT NOT NULL,
                discount_value REAL NOT NULL,
                max_discount_amount REAL,
                min_spend REAL NOT NULL DEFAULT 0,
                shop_id TEXT,
                shop_name TEXT,
                claim_url TEXT NOT NULL,
                guide TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                quality_score INTEGER NOT NULL DEFAULT 0,
                is_hot INTEGER NOT NULL DEFAULT 0,
                is_freeship INTEGER NOT NULL DEFAULT 0,
                start_time TEXT,
                end_time TEXT,
                last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_platform_voucher UNIQUE (platform_id, voucher_id_on_platform),
                CONSTRAINT chk_no_freeship CHECK (is_freeship = 0)
            );
            """)
            # Di chuyển dữ liệu cũ sang, lọc sạch freeship
            old_rows = cursor.execute("SELECT * FROM old_vouchers").fetchall()
            for r in old_rows:
                r_dict = dict(r)
                lbl = r_dict.get("label") or "Voucher"
                cat = r_dict.get("category") or ""
                vtype = r_dict.get("voucher_type") or "PLATFORM"
                # Bài trừ Freeship
                if "ship" in lbl.lower() or "ship" in cat.lower() or "ship" in vtype.lower():
                    continue
                v_code = r_dict.get("voucher_code")
                v_ext = r_dict.get("voucher_id") or v_code or str(r_dict.get("id"))
                cursor.execute("""
                INSERT OR IGNORE INTO vouchers (
                    id, platform_id, voucher_id_on_platform, voucher_code, voucher_type, category,
                    title, description, discount_type, discount_value, max_discount_amount, min_spend,
                    shop_id, claim_url, guide, status, quality_score, is_hot, is_freeship
                ) VALUES (?, 'SHOPEE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 80, 0, 0)
                """, (
                    f"SHOPEE_{v_ext}", v_ext, v_code, vtype, cat,
                    lbl, lbl, r_dict.get("discount_type") or "FIXED_AMOUNT",
                    float(r_dict.get("discount_val") or 0), float(r_dict.get("max_discount") or 0),
                    float(r_dict.get("min_spend") or 0), r_dict.get("shop_id"),
                    r_dict.get("claim_url") or "https://shopee.vn", r_dict.get("guide") or ""
                ))
            cursor.execute("DROP TABLE old_vouchers")
            conn.commit()

    # 2. Bảng Kho Voucher (Có khóa CHECK is_freeship = 0 để bài trừ Freeship tuyệt đối)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vouchers (
        id TEXT PRIMARY KEY,
        platform_id TEXT NOT NULL DEFAULT 'SHOPEE',
        voucher_id_on_platform TEXT NOT NULL,
        voucher_code TEXT,
        voucher_type TEXT NOT NULL, -- 'PLATFORM', 'SHOP', 'CATEGORY', 'LIVE_VIDEO'
        category TEXT,              -- 'Shopee Live', 'Shopee Video', 'Điện Tử'...
        title TEXT NOT NULL,
        description TEXT,
        discount_type TEXT NOT NULL, -- 'FIXED_AMOUNT', 'PERCENTAGE'
        discount_value REAL NOT NULL,
        max_discount_amount REAL,
        min_spend REAL NOT NULL DEFAULT 0,
        shop_id TEXT,
        shop_name TEXT,
        claim_url TEXT NOT NULL,
        guide TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE', -- 'UPCOMING', 'ACTIVE', 'EXHAUSTED', 'RESTOCKED', 'EXPIRED'
        quality_score INTEGER NOT NULL DEFAULT 0,
        is_hot INTEGER NOT NULL DEFAULT 0,
        is_freeship INTEGER NOT NULL DEFAULT 0,
        start_time TEXT,
        end_time TEXT,
        last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_platform_voucher UNIQUE (platform_id, voucher_id_on_platform),
        CONSTRAINT chk_no_freeship CHECK (is_freeship = 0)
    );
    """)

    # 3. Bảng Voucher Conditions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS voucher_conditions (
        id TEXT PRIMARY KEY,
        voucher_id TEXT NOT NULL,
        applies_to_category TEXT,
        is_new_user_only INTEGER NOT NULL DEFAULT 0,
        can_stack_with_shop INTEGER NOT NULL DEFAULT 1,
        can_stack_with_platform INTEGER NOT NULL DEFAULT 0,
        payment_method TEXT DEFAULT 'ALL',
        device_restriction TEXT DEFAULT 'ALL',
        required_action TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
    );
    """)

    # 4. Bảng Lịch sử trạng thái voucher (Restock radar)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS voucher_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id TEXT NOT NULL,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT,
        FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
    );
    """)

    # 5. Bảng Sản phẩm theo dõi (Products)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        platform_id TEXT NOT NULL DEFAULT 'SHOPEE',
        item_id_on_platform TEXT NOT NULL UNIQUE,
        shop_id TEXT,
        name TEXT NOT NULL,
        product_url TEXT NOT NULL,
        image_url TEXT,
        category_name TEXT,
        brand_name TEXT,
        target_mode TEXT DEFAULT 'PERCENT',
        target_value REAL DEFAULT 30,
        current_price REAL NOT NULL,
        baseline_market_price REAL NOT NULL,
        final_price REAL,
        discount_percent REAL DEFAULT 0,
        is_deal_ready INTEGER DEFAULT 0,
        applied_vouchers_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Đồng bộ các cột tương thích ngược giữa SQLite và schema mới
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    if cursor.fetchone():
        p_cols = [c[1] for c in cursor.execute("PRAGMA table_info(products)").fetchall()]
        if "item_id_on_platform" not in p_cols and "item_id" in p_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN item_id_on_platform TEXT")
            cursor.execute("UPDATE products SET item_id_on_platform = item_id WHERE item_id_on_platform IS NULL")
        if "platform_id" not in p_cols and "platform" in p_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN platform_id TEXT DEFAULT 'SHOPEE'")
            cursor.execute("UPDATE products SET platform_id = platform WHERE platform_id IS NULL")
        if "baseline_market_price" not in p_cols and "baseline_price" in p_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN baseline_market_price REAL")
            cursor.execute("UPDATE products SET baseline_market_price = baseline_price WHERE baseline_market_price IS NULL")
        if "baseline_price" not in p_cols and "baseline_market_price" in p_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN baseline_price REAL")
            cursor.execute("UPDATE products SET baseline_price = baseline_market_price WHERE baseline_price IS NULL")
        if "item_id" not in p_cols and "item_id_on_platform" in p_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN item_id TEXT")
            cursor.execute("UPDATE products SET item_id = item_id_on_platform WHERE item_id IS NULL")
        if "platform" not in p_cols and "platform_id" in p_cols:
            cursor.execute("ALTER TABLE products ADD COLUMN platform TEXT DEFAULT 'SHOPEE'")
            cursor.execute("UPDATE products SET platform = platform_id WHERE platform IS NULL")
        conn.commit()

    # 6. Bảng Lịch sử giá (Chống giá ảo)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT,
        item_id TEXT,
        price REAL NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
    if cursor.fetchone():
        ph_cols = [c[1] for c in cursor.execute("PRAGMA table_info(price_history)").fetchall()]
        if "product_id" not in ph_cols and "item_id" in ph_cols:
            cursor.execute("ALTER TABLE price_history ADD COLUMN product_id TEXT")
            cursor.execute("UPDATE price_history SET product_id = item_id WHERE product_id IS NULL")
        if "item_id" not in ph_cols and "product_id" in ph_cols:
            cursor.execute("ALTER TABLE price_history ADD COLUMN item_id TEXT")
            cursor.execute("UPDATE price_history SET item_id = product_id WHERE item_id IS NULL")
        conn.commit()

    # 7. Bảng Watchlist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watchlists (
        id TEXT PRIMARY KEY,
        target_type TEXT NOT NULL, -- 'PRODUCT_URL', 'KEYWORD', 'CATEGORY', 'BRAND'
        target_value TEXT NOT NULL,
        target_price REAL,
        min_discount_percent INTEGER DEFAULT 30,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 8. Bảng Khớp Voucher & Giá thực trả (Voucher Product Matches)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS voucher_product_matches (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        applied_voucher_ids TEXT NOT NULL,
        original_price REAL NOT NULL,
        shop_direct_discount REAL DEFAULT 0,
        shop_voucher_discount REAL DEFAULT 0,
        platform_voucher_discount REAL DEFAULT 0,
        category_live_voucher_discount REAL DEFAULT 0,
        final_price REAL NOT NULL,
        real_savings REAL NOT NULL,
        real_discount_percent REAL NOT NULL,
        stacking_confidence TEXT NOT NULL, -- 'VERIFIED', 'NEEDS_CHECK', 'CANNOT_STACK'
        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    );
    """)

    # 9. Bảng Cảnh Báo & Chống Trùng Lặp (Alert Events)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alert_events (
        id TEXT PRIMARY KEY,
        alert_type TEXT NOT NULL, -- 'HOT_VOUCHER', 'TARGET_MET', 'RESTOCKED_VOUCHER'
        dedup_hash TEXT NOT NULL UNIQUE,
        voucher_id TEXT,
        product_id TEXT,
        quality_score INTEGER,
        final_price REAL,
        message_payload TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 10. Bảng Cài đặt người dùng (User Settings)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        id TEXT PRIMARY KEY DEFAULT 'PERSONAL_USER',
        telegram_chat_id TEXT NOT NULL,
        min_quality_score INTEGER NOT NULL DEFAULT 70,
        min_save_amount REAL NOT NULL DEFAULT 50000,
        allow_new_user_vouchers INTEGER NOT NULL DEFAULT 0,
        active_platforms TEXT NOT NULL DEFAULT '["SHOPEE", "LAZADA", "TIKTOK"]',
        is_muted INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 11. Bảng Nhật ký sức khỏe connector (Connector Health Logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS connector_health_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_id TEXT NOT NULL,
        status TEXT NOT NULL, -- 'HEALTHY', 'DEGRADED', 'CIRCUIT_OPEN'
        latency_ms INTEGER NOT NULL,
        http_status INTEGER,
        error_message TEXT,
        circuit_state TEXT NOT NULL, -- 'CLOSED', 'OPEN', 'HALF_OPEN'
        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Đảm bảo có cột is_hidden
    try:
        cursor.execute("ALTER TABLE vouchers ADD COLUMN is_hidden INTEGER DEFAULT 0")
    except Exception:
        pass

    # Nạp 3 sàn mặc định nếu chưa có
    cursor.execute("""
    INSERT OR IGNORE INTO platforms (id, name, base_url, is_enabled, rate_limit_per_minute)
    VALUES 
    ('SHOPEE', 'Shopee Vietnam', 'https://shopee.vn', 1, 60),
    ('LAZADA', 'Lazada Vietnam', 'https://www.lazada.vn', 0, 30),
    ('TIKTOK', 'TikTok Shop Vietnam', 'https://shop.tiktok.com', 0, 30);
    """)

    # Dọn sạch triệt để mọi voucher Freeship còn sót từ bản cũ
    cursor.execute("""
    DELETE FROM vouchers 
    WHERE LOWER(voucher_type) LIKE '%ship%' 
       OR LOWER(title) LIKE '%freeship%' 
       OR LOWER(title) LIKE '%vận chuyển%'
       OR LOWER(title) LIKE '%phí ship%'
       OR LOWER(category) LIKE '%freeship%'
       OR is_freeship != 0;
    """)

    conn.commit()
    conn.close()

    # Khởi tạo các bảng mở rộng mới (voucher_changes, tracked_shops, notification_events, scan_runs)
    try:
        from repositories.voucher_repository import VoucherRepository
        from repositories.shop_repository import ShopRepository
        from repositories.scan_repository import ScanRepository
        VoucherRepository().init_schema()
        ShopRepository().init_schema()
        ScanRepository().init_schema()
    except Exception as e:
        print(f"[Database] Lưu ý khi tạo schema mở rộng: {e}")


# ----------------- CÁC HÀM TRUY XUẤT VOUCHER & PRODUCT -----------------

def upsert_voucher(voucher_data: Dict[str, Any]) -> bool:
    """Thêm hoặc cập nhật voucher với mã nhập tay và mã ẩn"""
    from app.core.junk_filter import is_freeship, validate_voucher

    # Kiểm tra bài trừ Freeship tuyệt đối
    is_ship, reason = is_freeship(voucher_data)
    if is_ship:
        return False

    is_valid, _ = validate_voucher(voucher_data, allow_new_user=voucher_data.get("allow_new_user", False))
    if not is_valid:
        return False

    v_id = str(voucher_data.get("id") or voucher_data.get("voucher_id") or f"{voucher_data.get('platform_id', 'SHOPEE')}_{voucher_data.get('voucher_id_on_platform') or voucher_data.get('voucher_code')}")
    plat_id = str(voucher_data.get("platform_id", "SHOPEE")).upper()
    v_ext_id = str(voucher_data.get("voucher_id_on_platform") or voucher_data.get("voucher_code") or v_id)
    v_code = str(voucher_data.get("voucher_code") or "").strip()
    v_type = str(voucher_data.get("voucher_type", "PLATFORM")).upper()
    category = voucher_data.get("category", "")
    title = str(voucher_data.get("title", ""))
    desc = voucher_data.get("description", "")
    d_type = str(voucher_data.get("discount_type", "FIXED_AMOUNT")).upper()
    d_val = float(voucher_data.get("discount_value") or voucher_data.get("discount_val") or 0.0)
    max_d = float(voucher_data.get("max_discount_amount") or voucher_data.get("max_discount") or 0.0)
    min_sp = float(voucher_data.get("min_spend") or 0.0)
    shop_id = str(voucher_data.get("shop_id")) if voucher_data.get("shop_id") else None
    shop_name = voucher_data.get("shop_name", "")
    claim_url = voucher_data.get("claim_url", "https://shopee.vn")
    guide = voucher_data.get("guide", "")
    status = str(voucher_data.get("status", "ACTIVE")).upper()
    is_hidden = 1 if (
        voucher_data.get("is_hidden") == 1 
        or "ẨN" in title.upper() 
        or "AN" in category.upper()
        or "SIEUHOI" in v_code.upper()
        or "SIÊU HỘI" in category.upper()
        or "SIÊU HỘI" in title.upper()
    ) else 0
    is_hot = 1 if (d_val >= 100000 or (d_type in ["PERCENTAGE", "PERCENT"] and d_val >= 15)) else 0

    start_time = voucher_data.get("start_time")
    end_time = voucher_data.get("end_time")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO vouchers (
        id, platform_id, voucher_id_on_platform, voucher_code, voucher_type, category,
        title, description, discount_type, discount_value, max_discount_amount, min_spend,
        shop_id, shop_name, claim_url, guide, status, quality_score, is_hot, is_freeship, is_hidden,
        start_time, end_time, last_verified_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 90, ?, 0, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(platform_id, voucher_id_on_platform) DO UPDATE SET
        voucher_code=excluded.voucher_code,
        voucher_type=excluded.voucher_type,
        category=excluded.category,
        title=excluded.title,
        description=excluded.description,
        discount_type=excluded.discount_type,
        discount_value=excluded.discount_value,
        max_discount_amount=excluded.max_discount_amount,
        min_spend=excluded.min_spend,
        shop_id=excluded.shop_id,
        shop_name=excluded.shop_name,
        claim_url=excluded.claim_url,
        guide=excluded.guide,
        status=excluded.status,
        is_hot=excluded.is_hot,
        is_hidden=excluded.is_hidden,
        start_time=excluded.start_time,
        end_time=excluded.end_time,
        last_verified_at=CURRENT_TIMESTAMP,
        updated_at=CURRENT_TIMESTAMP;
    """, (
        v_id, plat_id, v_ext_id, v_code, v_type, category,
        title, desc, d_type, d_val, max_d, min_sp,
        shop_id, shop_name, claim_url, guide, status, is_hot, is_hidden,
        start_time, end_time
    ))
    conn.commit()
    conn.close()
    return True

def get_vouchers(
    min_score: int = 0,
    hot_only: bool = False,
    hidden_only: bool = False,
    platform: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Lấy danh sách mã giảm giá, ưu tiên tối đa mã ẩn và mã nhập tay (đơn 0đ lên đầu)"""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT * FROM vouchers 
    WHERE is_freeship = 0 AND status IN ('ACTIVE', 'RESTOCKED')
    """
    params = []

    if hidden_only:
        query += " AND is_hidden = 1"
    elif hot_only:
        query += " AND (is_hot = 1 OR is_hidden = 1 OR discount_value >= 50000)"
    if platform and platform.upper() != "ALL":
        query += " AND platform_id = ?"
        params.append(platform.upper())

    # Ưu tiên số 1: Mã ẩn (is_hidden DESC)
    # Ưu tiên số 2: Đơn tối thiểu 0đ (min_spend = 0 DESC)
    # Ưu tiên số 3: Mức tiền giảm thực tế cao nhất (discount_value DESC)
    query += " ORDER BY is_hidden DESC, (min_spend = 0) DESC, discount_value DESC LIMIT 50"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_voucher_by_id(voucher_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vouchers WHERE id = ? OR voucher_id_on_platform = ? OR voucher_code = ?", (voucher_id, voucher_id, voucher_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def record_alert_event(
    alert_type: str,
    dedup_hash: str,
    message_payload: str,
    voucher_id: Optional[str] = None,
    product_id: Optional[str] = None,
    quality_score: Optional[int] = None,
    final_price: Optional[float] = None
) -> bool:
    """Ghi nhận cảnh báo và ngăn chặn trùng lặp"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        import uuid
        e_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO alert_events (id, alert_type, dedup_hash, voucher_id, product_id, quality_score, final_price, message_payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (e_id, alert_type, dedup_hash, voucher_id, product_id, quality_score, final_price, message_payload))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False # Đã gửi hash này rồi (trùng lặp)

def is_alert_duplicate(dedup_hash: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM alert_events WHERE dedup_hash = ?", (dedup_hash,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def log_connector_health(platform_id: str, status: str, latency_ms: int, circuit_state: str, http_status: Optional[int] = None, error: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO connector_health_logs (platform_id, status, latency_ms, http_status, error_message, circuit_state)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (platform_id, status, latency_ms, http_status, error, circuit_state))
    conn.commit()
    conn.close()

# Backward compatibility functions
def get_all_products():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_vouchers(active_only=True):
    return get_vouchers(min_score=0)

def add_product(item_id, shop_id, name, url, image_url, target_mode, target_value, baseline_price):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Kiểm tra xem sản phẩm đã tồn tại chưa
    cursor.execute("SELECT id FROM products WHERE item_id = ? OR item_id_on_platform = ?", (str(item_id), str(item_id)))
    exist = cursor.fetchone()
    if exist:
        cursor.execute("""
        UPDATE products SET
            name = ?,
            product_url = ?,
            image_url = ?,
            target_mode = ?,
            target_value = ?,
            baseline_price = ?,
            baseline_market_price = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (name, url, image_url, target_mode, target_value, baseline_price, baseline_price, exist[0]))
    else:
        cursor.execute("""
        INSERT INTO products (
            platform, platform_id, item_id, item_id_on_platform, shop_id,
            name, product_url, image_url, target_mode, target_value,
            baseline_price, baseline_market_price, current_price, final_price
        ) VALUES (
            'SHOPEE', 'SHOPEE', ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        """, (
            str(item_id), str(item_id), str(shop_id),
            name, url, image_url, target_mode, target_value,
            baseline_price, baseline_price, baseline_price, baseline_price
        ))
    conn.commit()
    conn.close()

def update_product_evaluation(item_id, current_price, final_price, discount_percent, is_deal_ready, applied_vouchers):
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
    WHERE item_id = ? OR item_id_on_platform = ?;
    """, (current_price, final_price, discount_percent, is_deal_ready, json.dumps(applied_vouchers, ensure_ascii=False), str(item_id), str(item_id)))
    
    # Ghi nhận lịch sử giá
    try:
        cursor.execute("INSERT INTO price_history (item_id, product_id, price) VALUES (?, ?, ?)", (str(item_id), str(item_id), current_price))
    except Exception:
        cursor.execute("INSERT INTO price_history (item_id, price) VALUES (?, ?)", (str(item_id), current_price))
    conn.commit()
    conn.close()

def delete_product(item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE item_id = ? OR item_id_on_platform = ?", (str(item_id), str(item_id)))
    conn.commit()
    conn.close()

def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    p_count = cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    r_count = cursor.execute("SELECT COUNT(*) FROM products WHERE is_deal_ready = 1").fetchone()[0]
    v_count = cursor.execute("SELECT COUNT(*) FROM vouchers WHERE is_freeship = 0 AND status IN ('ACTIVE', 'RESTOCKED')").fetchone()[0]
    hot_count = cursor.execute("SELECT COUNT(*) FROM vouchers WHERE is_freeship = 0 AND is_hot = 1").fetchone()[0]
    conn.close()
    return {
        "total_products": p_count,
        "ready_deals": r_count,
        "total_vouchers": v_count,
        "hot_vouchers": hot_count
    }

def get_product_by_id(item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE item_id = ? OR item_id_on_platform = ? OR id = ?", (str(item_id), str(item_id), str(item_id)))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_product_price_history(item_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT price, recorded_at FROM price_history WHERE item_id = ? OR product_id = ? ORDER BY id DESC LIMIT ?", (str(item_id), str(item_id), limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_settings() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_settings WHERE id = 'PERSONAL_USER'")
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT OR IGNORE INTO user_settings (id, telegram_chat_id) VALUES ('PERSONAL_USER', '8483531921')")
        conn.commit()
        cursor.execute("SELECT * FROM user_settings WHERE id = 'PERSONAL_USER'")
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_user_settings(key: str, value: Any):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE user_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 'PERSONAL_USER'", (value,))
    conn.commit()
    conn.close()
