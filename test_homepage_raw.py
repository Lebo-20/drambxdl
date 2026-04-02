import asyncio
import json
import httpx
from api import BASE_URL, DEFAULT_LANG

async def test_raw_homepage():
    url = f"{BASE_URL}/homepage"
    params = {"page": 1, "lang": DEFAULT_LANG}
    print(f"Requesting: {url} with {params}")
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        print(f"Status Code: {resp.status_code}")
        try:
             data = resp.json()
             if isinstance(data, list):
                  print(f"Items found: {len(data)}")
                  if data:
                       print(f"Item 1 ID: {data[0].get('bookId') or data[0].get('id')}")
                       print(f"Item 1 Title: {data[0].get('title') or data[0].get('bookName')}")
             elif isinstance(data, dict):
                  print(f"Sections found: {list(data.keys())}")
        except Exception as e:
             print(f"Error parsing JSON: {e}")
             print(f"Raw Response: {resp.text[:500]}")

if __name__ == "__main__":
    asyncio.run(test_raw_homepage())
