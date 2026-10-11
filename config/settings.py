import json
import os
from typing import List, Optional
from pydantic import BaseModel, Field

CONFIG_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

def _read_local_config():
    if os.path.exists(CONFIG_JSON_PATH):
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_local_cfg = _read_local_config()

class AppSettings(BaseModel):
    # Telegram Credentials
    telegram_bot_token: str = Field(
        default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN") 
        or _local_cfg.get("telegram", {}).get("bot_token", "")
    )
    telegram_chat_id: str = Field(
        default=os.environ.get("TELEGRAM_CHAT_ID") 
        or _local_cfg.get("telegram", {}).get("chat_id", "8483531921")
    )

    # Database & Cache
    database_url: str = Field(
        default=os.environ.get("DATABASE_URL", "sqlite:///deals.db")
    )
    redis_url: Optional[str] = Field(
        default=os.environ.get("REDIS_URL", None)
    )

    # Server Configuration
    host: str = Field(default=os.environ.get("HOST", "0.0.0.0"))
    port: int = Field(
        default=int(os.environ.get("PORT") or _local_cfg.get("settings", {}).get("web_port", 8000))
    )

    # Core Deal & Voucher Thresholds (Single Source of Truth)
    ELITE_MIN_FIXED_0D: float = Field(default=30000.0)    # Giảm tối thiểu 30.000đ cho đơn 0đ
    ELITE_MIN_PERCENT: float = Field(default=30.0)        # Giảm tối thiểu 30%
    ELITE_MIN_CAP: float = Field(default=30000.0)         # Trần giảm tối thiểu 30.000đ cho mã %
    ELITE_SCORE_NOTIFY: int = Field(default=70)           # Ngưỡng thông báo: >= 70 điểm (ĐÁNG LẤY)
    ELITE_SCORE_SUPER: int = Field(default=80)            # Ngưỡng thông báo: >= 80 điểm (SIÊU XỊN)

    hot_voucher_threshold: int = Field(default=80)        # >= 80 điểm là SIÊU XỊN
    min_alert_threshold: int = Field(default=70)          # >= 70 điểm là ĐÁNG LẤY
    min_save_amount: float = Field(default=30000.0)       # Giảm tối thiểu 30.000đ
    min_discount_percent: float = Field(default=30.0)     # Giảm tối thiểu 30%

    # Rate Limiting & Safety
    rate_limit_per_minute: int = Field(default=30)
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_recovery_seconds: int = Field(default=300) # 5 phút

    # Active Platforms
    active_platforms: List[str] = Field(default_factory=lambda: ["SHOPEE", "LAZADA", "TIKTOK"])

settings = AppSettings()
