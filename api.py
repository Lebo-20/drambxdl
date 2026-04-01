import httpx
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://drakula.dramabos.my.id/api/microdrama"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

async def get_drama_detail(book_id: str):
    url = f"{BASE_URL}/drama/{book_id}"
    params = {
        "lang": "id",
        "code": AUTH_CODE
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data and isinstance(data, dict):
                if data.get("success") and "data" in data:
                    return data["data"]
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching drama detail for {book_id}: {e}")
            return None

async def get_all_episodes(book_id: str):
    # For MicroDrama API, the episodes are returned inside the detail response
    detail = await get_drama_detail(book_id)
    if detail and "episodes" in detail:
        return detail["episodes"]
    return []

async def get_latest_dramas(pages=1, types=None):
    """Tries to find new dramas from verified API endpoints."""
    all_dramas = []
    
    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, pages + 1):
            url = f"{BASE_URL}/list"
            params = {
                "lang": "id",
                "code": AUTH_CODE,
                "page": page,
                "limit": 20
            }
            if types and isinstance(types, list) and len(types) > 0:
                params["type"] = types[0]
                
            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and "data" in data:
                        items_data = data["data"]
                        items = items_data.get("data", [])
                        if not items:
                            break
                        all_dramas.extend(items)
                    else:
                        break
                else:
                    break
            except Exception as e:
                logger.error(f"Error fetching list page {page}: {e}")
                break
    
    return all_dramas
