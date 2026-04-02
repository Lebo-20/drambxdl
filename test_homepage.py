import asyncio
import json
from api import get_homepage_dramas

async def test_homepage():
    print("Fetching Homepage...")
    home = await get_homepage_dramas(page=1)
    if home:
        if isinstance(home, list):
             print(f"Homepage (List of {len(home)} items)")
             # Print first item structure
             if home:
                 print(f"Item 1: {json.dumps(home[0], indent=2)}")
        elif isinstance(home, dict):
             print(f"Homepage (Dict with keys: {home.keys()})")
             # Print sections if they exist
             sections = home.get('data', [])
             if sections:
                  print(f"Found {len(sections)} sections")
                  for s in sections:
                       print(f"- Section: {s.get('name') or s.get('title')}")

if __name__ == "__main__":
    asyncio.run(test_homepage())
