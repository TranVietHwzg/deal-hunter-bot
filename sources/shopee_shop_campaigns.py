import os
import json
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sources.base_source import BaseVoucherSource
from repositories.shop_repository import ShopRepository
from core.voucher_filter import is_freeship
from models.voucher import VerificationStatus

VN_TZ = timezone(timedelta(hours=7))

class ShopeeShopCampaignSource(BaseVoucherSource):
    def __init__(self, shop_repo: Optional[ShopRepository] = None):
        super().__init__(
            name="shopee_shop_campaigns",
            source_type="SHOP_PAGE",
            rate_limit_per_minute=25,
            failure_threshold=4
        )
        self.shop_repo = shop_repo or ShopRepository()

    def get_shopee_cookie(self) -> Optional[str]:
        return os.environ.get("SHOPEE_COOKIE")

    async def _fetch_shop_api(self, client: httpx.AsyncClient, shop) -> List[Dict[str, Any]]:
        cookie = self.get_shopee_cookie()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://shopee.vn/{shop.shop_name or shop.shop_id}",
            "Accept": "application/json",
            "x-api-source": "pc",
            "x-shopee-language": "vi"
        }
        if cookie:
            headers["Cookie"] = cookie

        vouchers = []
        now_dt = datetime.now(VN_TZ)
        now_iso = now_dt.isoformat()

        urls = [
            f"https://shopee.vn/api/v4/voucher/batch_get_shop_vouchers?shopid={shop.shop_id}",
            f"https://shopee.vn/api/v2/voucher_wallet/get_shop_vouchers_by_shop_id?shop_id={shop.shop_id}"
        ]

        for url in urls:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_list = (
                        data.get("data", {}).get("vouchers") 
                        or data.get("data", {}).get("voucher_list")
                        or data.get("vouchers") 
                        or []
                    )
                    for v in raw_list:
                        code = v.get("voucher_code") or v.get("code")
                        raw_v_id = v.get("voucher_id") or v.get("promotionid")
                        claim_type = "CODE" if code else "SAVE_BUTTON"
                        d_val = float(v.get("discount_value") or v.get("amount") or v.get("coin_percentage") or 0)
                        max_d = float(v.get("max_discount") or v.get("discount_cap") or d_val)
                        min_sp = float(v.get("min_spend") or v.get("min_order_value") or 0)
                        is_pct = bool(v.get("discount_percentage") or v.get("coin_percentage") or d_val <= 100)
                        
                        start_ts = v.get("start_time")
                        end_ts = v.get("end_time")
                        
                        start_str = datetime.fromtimestamp(start_ts, tz=VN_TZ).strftime("%d/%m/%Y %H:%M") if start_ts else now_dt.strftime("%d/%m/%Y 00:00")
                        end_str = datetime.fromtimestamp(end_ts, tz=VN_TZ).strftime("%d/%m/%Y %H:%M") if end_ts else (now_dt + timedelta(days=7)).strftime("%d/%m/%Y 23:59")

                        v_status = VerificationStatus.VERIFIED_ACTIVE.value
                        if start_ts and datetime.fromtimestamp(start_ts, tz=VN_TZ) > now_dt:
                            v_status = VerificationStatus.VERIFIED_UPCOMING.value

                        shop_url = f"https://shopee.vn/{shop.shop_name or shop.shop_id}"
                        unique_suffix = code or raw_v_id or f"{int(d_val)}_{int(min_sp)}"
                        v_dict = {
                            "id": f"SHOP_{shop.shop_id}_{unique_suffix}",
                            "platform_voucher_id": str(raw_v_id) if raw_v_id else None,
                            "voucher_code": code,
                            "claim_type": claim_type,
                            "verification_status": v_status,
                            "title": f"Mã shop {shop.shop_name or shop.shop_id}: Giảm {int(d_val)}{'%' if is_pct else 'đ'}",
                            "description": v.get("description") or f"Voucher gian hàng chính hãng {shop.shop_name}",
                            "scope_type": "SHOP",
                            "shop_id": str(shop.shop_id),
                            "shop_name": shop.shop_name or f"Shop {shop.shop_id}",
                            "shop_url": shop_url,
                            "discount_type": "PERCENT" if is_pct else "FIXED",
                            "discount_value": d_val,
                            "max_discount": max_d,
                            "min_order_value": min_sp,
                            "start_time": start_str,
                            "end_time": end_str,
                            "source_url": shop_url,
                            "source_type": "SHOP_PAGE",
                            "source_title": f"Gian hàng {shop.shop_name or shop.shop_id}",
                            "source_captured_at": now_iso,
                            "source_evidence_excerpt": f"Shopee Shop API | {'Mã: ' + code if code else 'Voucher lưu ngay'} | Đơn từ {int(min_sp):,}đ",
                            "verified_at": now_iso,
                            "last_checked_at": now_iso,
                            "confidence_score": 98,
                            "is_freeship": 0
                        }
                        ship, _ = is_freeship(v_dict)
                        if not ship:
                            vouchers.append(v_dict)
                    if vouchers:
                        break
            except Exception:
                continue

        return vouchers

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Thu thập voucher từ các shop nằm trong danh sách theo dõi cá nhân"""
        if not self.circuit_breaker.can_execute():
            return []

        tracked = self.shop_repo.get_tracked_shops(enabled_only=True)
        if not tracked:
            # Tự động gieo mầm (seed) các gian hàng Mall công nghệ mục tiêu để không bị sót voucher shop
            try:
                self.shop_repo.add_shop("318414434", "Anker Official Store", "https://shopee.vn/anker_official_store_vn")
                self.shop_repo.add_shop("290130836", "Baseus Official Mall", "https://shopee.vn/baseus_official_mall")
                tracked = self.shop_repo.get_tracked_shops(enabled_only=True)
            except Exception:
                pass

        if not tracked:
            self.status = "NO_SHOPS_CONFIGURED"
            return []
        
        self.status = "HEALTHY"

        await self.rate_limiter.acquire()

        results = []
        for shop in tracked:
            self.shop_repo.update_last_scan(shop.shop_id)

        # 1. Thử cào trực tiếp qua Shopee API (đặc biệt khi có SHOPEE_COOKIE)
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                for shop in tracked:
                    live_vouchers = await self._fetch_shop_api(client, shop)
                    results.extend(live_vouchers)
        except Exception as e:
            print(f"[ShopeeShopCampaignSource] Lỗi cào live shop: {e}")

        # 2. Bổ sung từ file data/shop_vouchers.json nếu có
        shop_vouchers_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "shop_vouchers.json")
        if os.path.exists(shop_vouchers_file):
            try:
                with open(shop_vouchers_file, "r", encoding="utf-8") as f:
                    shop_data = json.load(f)
                tracked_ids = {str(s.shop_id).lower() for s in tracked}
                seen_codes = {v.get("voucher_code") for v in results if v.get("voucher_code")}
                for item in shop_data:
                    code = item.get("voucher_code")
                    if str(item.get("shop_id", "")).lower() in tracked_ids and code not in seen_codes:
                        ship, _ = is_freeship(item)
                        if not ship:
                            results.append(item)
            except Exception:
                pass

        self.circuit_breaker.record_success()
        return results

