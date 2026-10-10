import sys
import httpx
import asyncio
import re

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    url = 'https://www.bing.com/search?q=site%3Ashopee.vn+%2224515279749%22'
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        print('Status:', r.status_code)
        matches = re.findall(r'(\b\d{1,3}(?:\.\d{3})*\s*₫|\b\d{1,3}(?:\.\d{3})*\s*đ|\b₫\s*\d{1,3}(?:\.\d{3})*)', r.text)
        print('Price matches in Bing:', matches)
        snippets = re.findall(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', r.text)
        for s in snippets:
            clean = re.sub(r'<[^>]+>', '', s)
            print('Snippet:', clean)

if __name__ == "__main__":
    asyncio.run(main())
