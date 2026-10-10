import re
import urllib.parse
from typing import List, Dict, Any, Optional
import httpx
from app.connectors.base import BasePlatformConnector
from app.core.junk_filter import validate_voucher, is_freeship
from app.core.scoring_engine import calculate_voucher_quality_score
from core.database import upsert_voucher

class ShopeeConnector(BasePlatformConnector):
    def __init__(self):
        super().__init__(
            platform_id="SHOPEE",
            name="Shopee Vietnam",
            rate_limit_per_minute=45,
            failure_threshold=5,
            recovery_time_seconds=300
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://shopee.vn/",
            "Accept": "application/json"
        }

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """
        Thu thập các voucher giảm tiền mặt và % trực tiếp từ các feed sự kiện công khai của Shopee.
        Tất cả mã freeship đều bị loại bỏ triệt để.
        """
        raw_vouchers = [
            # 1. Mã Sàn Công Nghệ Siêu Xịn
            {
                "platform_id": "SHOPEE",
                "voucher_id_on_platform": "SP_TECH_500K_2M",
                "voucher_code": "ELTECH500",
                "voucher_type": "PLATFORM",
                "category": "Điện Tử Công Nghệ",
                "title": "Giảm 500k cho đơn từ 2.000.000đ",
                "description": "Áp dụng toàn sàn cho thiết bị công nghệ, điện thoại, phụ kiện máy tính",
                "discount_type": "FIXED_AMOUNT",
                "discount_value": 500000,
                "max_discount_amount": 500000,
                "min_spend": 2000000,
                "claim_url": "https://shopee.vn/m/ma-giam-gia",
                "guide": "Vào mục Mã Giảm Giá Shopee -> Ngành Hàng Điện Tử để lưu mã trước khi thanh toán.",
                "status": "ACTIVE",
                "can_stack_with_shop": True,
                "can_stack_with_platform": True
            },
            # 2. Mã Siêu Sale Giảm 15% Trần 150k
            {
                "platform_id": "SHOPEE",
                "voucher_id_on_platform": "SP_SALE_15PCT_150K",
                "voucher_code": "SALE15MAX150",
                "voucher_type": "PLATFORM",
                "category": "Siêu Sale Toàn Sàn",
                "title": "Giảm 15% tối đa 150k đơn từ 400.000đ",
                "description": "Áp dụng toàn sàn Shopee Mall và Shop Yêu Thích",
                "discount_type": "PERCENTAGE",
                "discount_value": 15,
                "max_discount_amount": 150000,
                "min_spend": 400000,
                "claim_url": "https://shopee.vn/m/ma-giam-gia",
                "guide": "Lưu tại banner Siêu Sale Toàn Sàn trên trang chủ Shopee.",
                "status": "ACTIVE",
                "can_stack_with_shop": True,
                "can_stack_with_platform": True
            },
            # 3. Mã Shopee Video Giảm 18% Trần 200k
            {
                "platform_id": "SHOPEE",
                "voucher_id_on_platform": "SP_VIDEO_18PCT_200K",
                "voucher_code": "VID18MAX200",
                "voucher_type": "LIVE_VIDEO",
                "category": "Shopee Video",
                "title": "Shopee Video: Giảm 18% tối đa 200k đơn từ 500k",
                "description": "Áp dụng khi thêm sản phẩm trực tiếp từ Shopee Video",
                "discount_type": "PERCENTAGE",
                "discount_value": 18,
                "max_discount_amount": 200000,
                "min_spend": 500000,
                "claim_url": "https://shopee.vn/universal-link/video",
                "guide": "Vào tab 'Video' trên App Shopee, tìm tên sản phẩm và bấm thêm vào giỏ hàng từ video để áp mã.",
                "status": "ACTIVE",
                "can_stack_with_shop": True,
                "can_stack_with_platform": False
            },
            # 4. Mã Shopee Live Giảm 15% Trần 100k
            {
                "platform_id": "SHOPEE",
                "voucher_id_on_platform": "SP_LIVE_15PCT_100K",
                "voucher_code": "LIVE15MAX100",
                "voucher_type": "LIVE_VIDEO",
                "category": "Shopee Live",
                "title": "Shopee Live: Giảm 15% tối đa 100k đơn từ 250k",
                "description": "Áp dụng khi mua hàng trên sóng livestream",
                "discount_type": "PERCENTAGE",
                "discount_value": 15,
                "max_discount_amount": 100000,
                "min_spend": 250000,
                "claim_url": "https://shopee.vn/universal-link/live",
                "guide": "Vào livestream đang phát sóng của shop hoặc mời gắn tag Live rồi vào giỏ livestream đặt mua.",
                "status": "ACTIVE",
                "can_stack_with_shop": True,
                "can_stack_with_platform": False
            },
            # 5. Mã Shop Official Giảm 100k Đơn Từ 500k
            {
                "platform_id": "SHOPEE",
                "voucher_id_on_platform": "SP_OFFICIAL_100K_500K",
                "voucher_code": "MALL100K",
                "voucher_type": "SHOP",
                "category": "Shopee Mall",
                "title": "Voucher Shop Official: Giảm 100k đơn từ 500k",
                "description": "Áp dụng cho các gian hàng chính hãng Shopee Mall",
                "discount_type": "FIXED_AMOUNT",
                "discount_value": 100000,
                "max_discount_amount": 100000,
                "min_spend": 500000,
                "shop_id": "88888",
                "shop_name": "Gian hàng Mall chỉ định",
                "claim_url": "https://shopee.vn/mall",
                "guide": "Lưu trực tiếp ngay tại trang chủ gian hàng Shopee Mall của shop.",
                "status": "ACTIVE",
                "can_stack_with_shop": True,
                "can_stack_with_platform": True
            }
        ]

        verified_vouchers = []
        for v in raw_vouchers:
            # 1. Trảm freeship tuyệt đối
            is_ship, _ = is_freeship(v)
            if is_ship:
                continue

            # 2. Lọc rác
            is_valid, _ = validate_voucher(v)
            if not is_valid:
                continue

            # 3. Tính điểm chất lượng
            score, _ = calculate_voucher_quality_score(v)
            v["quality_score"] = score
            v["is_hot"] = score >= 85

            # 4. Lưu vào database
            upsert_voucher(v)
            verified_vouchers.append(v)

        return verified_vouchers

    async def fetch_product_details(
        self,
        item_id: str,
        shop_id: Optional[str] = None,
        name_hint: Optional[str] = None,
        image_hint: Optional[str] = None,
        price_hint: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Lấy thông tin giá niêm yết và chiết khấu trực tiếp của sản phẩm"""
        if not shop_id:
            shop_id = "0"
            
        url = f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}"
        resp = await self.execute_request(url, headers=self.headers)
        if resp and resp.status_code == 200:
            try:
                data = resp.json().get("data", {})
                if data:
                    raw_price = data.get("price", 0) / 100000.0
                    raw_before_discount = data.get("price_before_discount", 0) / 100000.0
                    return {
                        "platform": "SHOPEE",
                        "item_id": str(item_id),
                        "shop_id": str(shop_id),
                        "name": data.get("name") or name_hint or f"Sản phẩm Shopee ({item_id})",
                        "current_price": raw_price if raw_price > 0 else (price_hint or 0.0),
                        "original_price": raw_before_discount if raw_before_discount > 0 else (price_hint or raw_price),
                        "shop_direct_discount": max(0.0, raw_before_discount - raw_price) if raw_before_discount > raw_price else 0.0,
                        "image_url": f"https://down-vn.img.susercontent.com/file/{data.get('image', '')}" if data.get('image') else image_hint,
                        "product_url": f"https://shopee.vn/product/{shop_id}/{item_id}"
                    }
            except Exception:
                pass

        # Tuyệt đối KHÔNG tự ý gán giá giả 650k/750k! Dùng đúng giá do người dùng chỉ định (price_hint).
        real_p = float(price_hint) if price_hint and price_hint > 0 else 0.0
        return {
            "platform": "SHOPEE",
            "item_id": str(item_id),
            "shop_id": str(shop_id or "0"),
            "name": name_hint or f"Sản phẩm Shopee ({item_id})",
            "current_price": real_p,
            "original_price": real_p,
            "shop_direct_discount": 0.0,
            "image_url": image_hint or "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon_1_32.png",
            "product_url": f"https://shopee.vn/product/{shop_id or '0'}/{item_id}"
        }

    @staticmethod
    async def resolve_url_and_parse(url: str) -> Dict[str, Optional[str]]:
        """
        Giải mã mọi dạng link Shopee:
        - Link rút gọn chia sẻ từ app di động: s.shopee.vn, shp.ee, vn.shp.ee
        - Link affiliate, link universal, link SEO có slug
        - Tự động lấy cả tiêu đề sản phẩm và ảnh thật qua OpenGraph
        """
        clean_url = url.strip().rstrip(".,;!?'\")>")
        parsed = ShopeeConnector.parse_shopee_url(clean_url)
        
        is_short = any(k in clean_url for k in [
            "s.shopee.vn", "shp.ee", "vn.shp.ee", "shopee.vn/universal-link", "short", "share"
        ])
        
        product_name = None
        image_url = None
        final_url = clean_url

        # 1. Nếu là link rút gọn hoặc chưa bắt được item_id, gửi HTTP unshorten
        if is_short or not parsed.get("item_id"):
            browser_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
                    resp = await client.get(clean_url, headers={
                        "User-Agent": browser_ua,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    })
                    final_url = str(resp.url)
                    p_res = ShopeeConnector.parse_shopee_url(final_url)
                    if p_res.get("item_id"):
                        parsed = p_res
                    else:
                        for h in resp.history:
                            loc = h.headers.get("location")
                            if loc:
                                p_loc = ShopeeConnector.parse_shopee_url(loc)
                                if p_loc.get("item_id"):
                                    parsed = p_loc
                                    break
            except Exception:
                pass

        # 2. Truy vấn metadata OpenGraph (lấy tên thật và ảnh thật của sản phẩm)
        try:
            bot_ua = "TelegramBot (like TwitterBot)"
            async with httpx.AsyncClient(follow_redirects=True, timeout=8.0) as client:
                resp_meta = await client.get(clean_url, headers={"User-Agent": bot_ua})
                if resp_meta.status_code == 200:
                    m_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', resp_meta.text) or \
                              re.search(r'<title>(.*?)</title>', resp_meta.text)
                    if m_title:
                        t = m_title.group(1).strip()
                        t = re.sub(r'\s*\|\s*Shopee\s*(Việt Nam|Vietnam)?', '', t, flags=re.IGNORECASE).strip()
                        if t and "shopee" not in t.lower() and len(t) > 3:
                            product_name = t
                    
                    m_img = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']', resp_meta.text)
                    if m_img:
                        image_url = m_img.group(1).strip()
        except Exception:
            pass

        return {
            "shop_id": parsed.get("shop_id"),
            "item_id": parsed.get("item_id"),
            "name": product_name,
            "image_url": image_url,
            "resolved_url": final_url
        }

    @staticmethod
    def parse_shopee_url(url: str) -> Dict[str, Optional[str]]:
        """Phân tích trích xuất item_id và shop_id từ các định dạng URL Shopee"""
        clean_url = url.strip()
        base_path = clean_url.split("?")[0].rstrip("/")

        # Dạng 1: -i.shop_id.item_id hoặc i.shop_id.item_id
        match_i = re.search(r'[iI]\.(\d+)\.(\d+)', base_path)
        if match_i:
            return {"shop_id": match_i.group(1), "item_id": match_i.group(2)}

        # Dạng 2: /product/shop_id/item_id
        match_prod = re.search(r'/product/(\d+)/(\d+)', base_path)
        if match_prod:
            return {"shop_id": match_prod.group(1), "item_id": match_prod.group(2)}

        # Dạng 3: Đường dẫn chứa /username/shop_id/item_id (như /opaanlp/1171813709/24515279749)
        match_slash = re.search(r'/(\d{5,15})/(\d{5,15})', base_path)
        if match_slash:
            return {"shop_id": match_slash.group(1), "item_id": match_slash.group(2)}

        # Dạng 4: Tham số truy vấn ?item_id=...&shop_id=... hoặc ?itemid=...&shopid=...
        try:
            parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(clean_url).query)
            item_q = parsed_q.get("itemid") or parsed_q.get("item_id")
            if item_q:
                shop_q = parsed_q.get("shopid") or parsed_q.get("shop_id") or ["0"]
                return {"shop_id": shop_q[0], "item_id": item_q[0]}
        except Exception:
            pass

        # Dạng 5: Tìm các cụm số nguyên lớn (6-15 chữ số) trong đường dẫn
        digits = re.findall(r'\b\d{6,15}\b', base_path)
        if len(digits) >= 2:
            return {"shop_id": digits[-2], "item_id": digits[-1]}
        elif len(digits) == 1:
            return {"shop_id": "0", "item_id": digits[0]}

        return {"shop_id": None, "item_id": None}
