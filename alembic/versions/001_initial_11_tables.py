"""initial_11_tables

Revision ID: 001_initial_11_tables
Revises: 
Create Date: 2026-10-10 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial_11_tables'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # 1. Platforms
    op.execute("""
    CREATE TABLE IF NOT EXISTS platforms (
        id VARCHAR(20) PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        base_url VARCHAR(255) NOT NULL,
        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        rate_limit_per_minute INT NOT NULL DEFAULT 60,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Vouchers với CHECK is_freeship = FALSE
    op.execute("""
    CREATE TABLE IF NOT EXISTS vouchers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        platform_id VARCHAR(20) NOT NULL REFERENCES platforms(id),
        voucher_id_on_platform VARCHAR(100) NOT NULL,
        voucher_code VARCHAR(100),
        voucher_type VARCHAR(30) NOT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        discount_type VARCHAR(20) NOT NULL,
        discount_value DECIMAL(12, 2) NOT NULL,
        max_discount_amount DECIMAL(12, 2),
        min_spend DECIMAL(12, 2) NOT NULL DEFAULT 0,
        shop_id VARCHAR(100),
        shop_name VARCHAR(255),
        claim_url TEXT NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        quality_score INT NOT NULL DEFAULT 0,
        is_hot BOOLEAN NOT NULL DEFAULT FALSE,
        is_freeship BOOLEAN NOT NULL DEFAULT FALSE,
        start_time TIMESTAMPTZ,
        end_time TIMESTAMPTZ,
        last_verified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_platform_voucher UNIQUE (platform_id, voucher_id_on_platform),
        CONSTRAINT chk_no_freeship CHECK (is_freeship = FALSE)
    );
    """)

    # 3. Voucher Conditions
    op.execute("""
    CREATE TABLE IF NOT EXISTS voucher_conditions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        voucher_id UUID NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        applies_to_category VARCHAR(100),
        is_new_user_only BOOLEAN NOT NULL DEFAULT FALSE,
        can_stack_with_shop BOOLEAN NOT NULL DEFAULT TRUE,
        can_stack_with_platform BOOLEAN NOT NULL DEFAULT FALSE,
        payment_method VARCHAR(50),
        device_restriction VARCHAR(30),
        required_action TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. Voucher Status History
    op.execute("""
    CREATE TABLE IF NOT EXISTS voucher_status_history (
        id BIGSERIAL PRIMARY KEY,
        voucher_id UUID NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        previous_status VARCHAR(20) NOT NULL,
        new_status VARCHAR(20) NOT NULL,
        detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    );
    """)

    # 5. Products
    op.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        platform_id VARCHAR(20) NOT NULL REFERENCES platforms(id),
        item_id_on_platform VARCHAR(100) NOT NULL,
        shop_id VARCHAR(100),
        name VARCHAR(500) NOT NULL,
        product_url TEXT NOT NULL,
        image_url TEXT,
        category_name VARCHAR(100),
        brand_name VARCHAR(100),
        current_price DECIMAL(12, 2) NOT NULL,
        baseline_market_price DECIMAL(12, 2) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_platform_item UNIQUE (platform_id, item_id_on_platform)
    );
    """)

    # 6. Price History
    op.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id BIGSERIAL PRIMARY KEY,
        product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        price DECIMAL(12, 2) NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. Watchlists
    op.execute("""
    CREATE TABLE IF NOT EXISTS watchlists (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        target_type VARCHAR(20) NOT NULL,
        target_value TEXT NOT NULL,
        target_price DECIMAL(12, 2),
        min_discount_percent INT DEFAULT 30,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 8. Voucher Product Matches
    op.execute("""
    CREATE TABLE IF NOT EXISTS voucher_product_matches (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        applied_voucher_ids JSONB NOT NULL,
        original_price DECIMAL(12, 2) NOT NULL,
        shop_direct_discount DECIMAL(12, 2) NOT NULL DEFAULT 0,
        shop_voucher_discount DECIMAL(12, 2) NOT NULL DEFAULT 0,
        platform_voucher_discount DECIMAL(12, 2) NOT NULL DEFAULT 0,
        category_live_voucher_discount DECIMAL(12, 2) NOT NULL DEFAULT 0,
        final_price DECIMAL(12, 2) NOT NULL,
        real_savings DECIMAL(12, 2) NOT NULL,
        real_discount_percent DECIMAL(5, 2) NOT NULL,
        stacking_confidence VARCHAR(20) NOT NULL,
        evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 9. Alert Events
    op.execute("""
    CREATE TABLE IF NOT EXISTS alert_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        alert_type VARCHAR(30) NOT NULL,
        dedup_hash VARCHAR(64) NOT NULL UNIQUE,
        voucher_id UUID REFERENCES vouchers(id) ON DELETE SET NULL,
        product_id UUID REFERENCES products(id) ON DELETE SET NULL,
        quality_score INT,
        final_price DECIMAL(12, 2),
        message_payload TEXT NOT NULL,
        sent_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 10. User Settings
    op.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        id VARCHAR(50) PRIMARY KEY DEFAULT 'PERSONAL_USER',
        telegram_chat_id VARCHAR(50) NOT NULL,
        min_quality_score INT NOT NULL DEFAULT 70,
        min_save_amount DECIMAL(12, 2) NOT NULL DEFAULT 50000,
        allow_new_user_vouchers BOOLEAN NOT NULL DEFAULT FALSE,
        active_platforms JSONB NOT NULL DEFAULT '["SHOPEE", "LAZADA", "TIKTOK"]',
        is_muted BOOLEAN NOT NULL DEFAULT FALSE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 11. Connector Health Logs
    op.execute("""
    CREATE TABLE IF NOT EXISTS connector_health_logs (
        id BIGSERIAL PRIMARY KEY,
        platform_id VARCHAR(20) NOT NULL REFERENCES platforms(id),
        status VARCHAR(20) NOT NULL,
        latency_ms INT NOT NULL,
        http_status INT,
        error_message TEXT,
        circuit_state VARCHAR(20) NOT NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

def downgrade():
    op.execute("DROP TABLE IF EXISTS connector_health_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_settings CASCADE;")
    op.execute("DROP TABLE IF EXISTS alert_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS voucher_product_matches CASCADE;")
    op.execute("DROP TABLE IF EXISTS watchlists CASCADE;")
    op.execute("DROP TABLE IF EXISTS price_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS products CASCADE;")
    op.execute("DROP TABLE IF EXISTS voucher_status_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS voucher_conditions CASCADE;")
    op.execute("DROP TABLE IF EXISTS vouchers CASCADE;")
    op.execute("DROP TABLE IF EXISTS platforms CASCADE;")
