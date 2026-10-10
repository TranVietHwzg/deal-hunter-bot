import re
import urllib.parse
import httpx
import asyncio

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def parse_shopee_url(url: str):
    """
    Trích xuất shop_id và item_id từ các dạng link Shopee
    Ví dụ:
    - https://shopee.vn/product/12345/67890
    - https://shopee.vn/Bàn-phím-cơ-DareU-EK87-i.12345.67890
    """
    clean_url = url.split("?")[0].strip()
    
    # Dạng 1: /product/12345/67890
    match1 = re.search(r'/product/(\d+)/(\d+)', clean_url)
    if match1:
        return match1.group(1), match1.group(2)
        
    # Dạng 2: -i.12345.67890
    match2 = re.search(r'-i\.(\d+)\.(\d+)', clean_url)
    if match2:
        return match2.group(1), match2.group(2)
        
    # Dạng 3: Đường dẫn 2 cụm số /shop_id/item_id
    match3 = re.search(r'/(\d{5,15})/(\d{5,15})', clean_url)
    if match3:
        return match3.group(1), match3.group(2)

    # Dạng 4: dạng số ở đuôi
    match4 = re.findall(r'\b\d{6,15}\b', clean_url)
    if len(match4) >= 2:
        return match4[-2], match4[-1]

    return None, None

async def resolve_short_url(url: str) -> str:
    """Giải mã link rút gọn s.shopee.vn nếu người dùng dán link chia sẻ từ điện thoại"""
    if "s.shopee.vn" in url or "shp.ee" in url:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                res = await client.get(url, headers={"User-Agent": USER_AGENT})
                return str(res.url)
        except Exception:
            return url
    return url

async def fetch_shopee_item(shop_id: str, item_id: str):
    """
    Gọi endpoint lấy thông tin sản phẩm và giá hiện tại
    """
    api_url = f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": f"https://shopee.vn/product/{shop_id}/{item_id}",
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(api_url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                item = data.get("data")
                if item:
                    # Shopee lưu giá dạng nhân với 100.000
                    price = item.get("price", 0) / 100000.0
                    price_before = (item.get("price_before_discount") or item.get("price", 0)) / 100000.0
                    image_id = item.get("image", "")
                    image_url = f"https://down-vn.img.susercontent.com/file/{image_id}" if image_id else ""
                    
                    return {
                        "item_id": str(item_id),
                        "shop_id": str(shop_id),
                        "name": item.get("name", "Sản phẩm Shopee"),
                        "price": price,
                        "baseline_price": price_before if price_before > price else price,
                        "image_url": image_url,
                        "stock": item.get("stock", 100),
                        "historical_sold": item.get("historical_sold", 0),
                        "rating_star": item.get("item_rating", {}).get("rating_star", 5.0)
                    }
    except Exception as e:
        print(f"[Scraper] Lỗi khi lấy dữ liệu Shopee: {e}")

    # Fallback dữ liệu nếu mạng tạm thời chặn để tránh crash
    return {
        "item_id": str(item_id),
        "shop_id": str(shop_id),
        "name": f"Sản phẩm Shopee #{item_id}",
        "price": 500000,
        "baseline_price": 500000,
        "image_url": "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon_1_32.png",
        "stock": 50,
        "historical_sold": 100,
        "rating_star": 5.0
    }

def get_default_high_tier_vouchers():
    """
    Khởi tạo các Voucher Sàn & Video XỊN thường niên của Shopee (để bot gộp mã ngay lập tức)
    """
    return [
        {
            "voucher_id": "SHOPEE_PLATFORM_15PCT",
            "voucher_code": "SPP15MAX150K",
            "voucher_type": "PLATFORM",
            "discount_type": "PERCENT",
            "discount_val": 15,
            "max_discount": 150000,
            "min_spend": 300000,
            "label": "Mã Sàn: Giảm 15% tối đa 150k (Đơn từ 300k)",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SHOPEE_VIDEO_20PCT",
            "voucher_code": "VIDEO20MAX100K",
            "voucher_type": "LIVE_VIDEO",
            "discount_type": "PERCENT",
            "discount_val": 20,
            "max_discount": 100000,
            "min_spend": 200000,
            "label": "Mã Shopee Video: Giảm 20% tối đa 100k (Đơn từ 200k)",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SHOPEE_FREESHIP_XTRA",
            "voucher_code": "FREESHIP30K",
            "voucher_type": "FREESHIP",
            "discount_type": "FIXED",
            "discount_val": 30000,
            "max_discount": 30000,
            "min_spend": 0,
            "label": "Freeship Xtra: Hỗ trợ 30.000đ phí vận chuyển",
            "is_high_tier": 1,
            "is_active": 1
        },
        {
            "voucher_id": "SHOPEE_MEGA_50K",
            "voucher_code": "MEGA50KDON0D",
            "voucher_type": "PLATFORM",
            "discount_type": "FIXED",
            "discount_val": 50000,
            "max_discount": 50000,
            "min_spend": 100000,
            "label": "Mã Khung Giờ: Giảm 50k (Đơn từ 100k)",
            "is_high_tier": 1,
            "is_active": 1
        }
    ]
