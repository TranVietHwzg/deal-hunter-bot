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

    # Core Deal & Voucher Thresholds
    hot_voucher_threshold: int = Field(default=85)    # >= 85 điểm là HOT
    min_alert_threshold: int = Field(default=70)      # >= 70 điểm mới gửi cảnh báo thường
    min_save_amount: float = Field(default=50000.0)   # Giảm tối thiểu 50.000đ
    min_discount_percent: float = Field(default=15.0) # Hoặc giảm tối thiểu 15%

    # Rate Limiting & Safety
    rate_limit_per_minute: int = Field(default=30)
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_recovery_seconds: int = Field(default=300) # 5 phút

    # Active Platforms
    active_platforms: List[str] = Field(default_factory=lambda: ["SHOPEE", "LAZADA", "TIKTOK"])

settings = AppSettings()
