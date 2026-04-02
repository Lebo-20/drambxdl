import httpx
import logging

logger = logging.getLogger(__name__)

# New API Configuration
BASE_URL = "https://dramabox.dramabos.my.id/api/v1"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"
DEFAULT_LANG = "in"

async def get_drama_detail(book_id: str):
    """Fetches drama detail from the new Dramabox API."""
    url = f"{BASE_URL}/detail"
    params = {
        "bookId": book_id,
        "lang": DEFAULT_LANG,
        "code": AUTH_CODE
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if data.get("success") and "data" in data:
                    return data["data"]
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching drama detail for {book_id}: {e}")
            return None

async def get_all_episodes(book_id: str):
    """Fetches all episodes for a drama from the new Dramabox API."""
    url = f"{BASE_URL}/allepisode"
    params = {
        "bookId": book_id,
        "lang": DEFAULT_LANG,
        "code": AUTH_CODE
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if data.get("success") and "data" in data:
                    return data["data"]
                if "episodes" in data:
                    return data["episodes"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error fetching episodes for {book_id}: {e}")
            return []

async def get_latest_dramas(page=1):
    """Fetches latest dramas from the new Dramabox API."""
    url = f"{BASE_URL}/latest"
    params = {
        "lang": DEFAULT_LANG,
        "page": page
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list): return data
                if data.get("success") and "data" in data:
                    return data["data"]
            return []
        except Exception as e:
            logger.error(f"Error fetching latest dramas: {e}")
            return []

async def get_dubbed_dramas(page=1, classify="terpopuler"):
    """Fetches dubbed dramas from the new Dramabox API."""
    url = f"{BASE_URL}/dubbed"
    params = {
        "classify": classify,
        "page": page,
        "lang": DEFAULT_LANG
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list): return data
                if data.get("success") and "data" in data:
                    return data["data"]
            return []
        except Exception as e:
            logger.error(f"Error fetching dubbed dramas: {e}")
            return []

async def get_foryou_dramas():
    """Fetches dramas from 'For You' section."""
    url = f"{BASE_URL}/foryou"
    params = {"lang": DEFAULT_LANG}
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list): return data
                if data.get("success") and "data" in data:
                    return data["data"]
            return []
        except Exception as e:
            logger.error(f"Error fetching for-you dramas: {e}")
            return []

async def get_popular_search():
    """Fetches popular search dramas."""
    url = f"{BASE_URL}/populersearch"
    params = {"lang": DEFAULT_LANG}
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list): return data
                if data.get("success") and "data" in data:
                    return data["data"]
            return []
        except Exception as e:
            logger.error(f"Error fetching popular search: {e}")
            return []

async def get_homepage_dramas(page=1):
    """Fetches dramas from the homepage sections."""
    url = f"{BASE_URL}/homepage"
    params = {
        "page": page,
        "lang": DEFAULT_LANG
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                
                # If it's a dict with sections
                all_home = []
                if isinstance(data, dict):
                    # Combine common sections
                    for key in ['topList', 'recommendList', 'hotList', 'data']:
                        section = data.get(key, [])
                        if isinstance(section, list):
                            all_home.extend(section)
                return all_home
            return []
        except Exception as e:
            logger.error(f"Error fetching homepage: {e}")
            return []
async def search_dramas(query: str, page=1):
    """Searches for dramas using the new Dramabox API."""
    url = f"{BASE_URL}/search"
    params = {
        "query": query,
        "page": page,
        "lang": DEFAULT_LANG
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and "data" in data:
                    return data["data"]
            return []
        except Exception as e:
            logger.error(f"Error searching dramas: {e}")
            return []

# Backwards compatibility / Mapping for main.py
async def get_latest_idramas(pages=1):
    # Map to dubbed or homepage for now to maintain structure
    return await get_dubbed_dramas(page=pages)

async def get_idrama_detail(book_id: str):
    return await get_drama_detail(book_id)

async def get_idrama_all_episodes(book_id: str):
    return await get_all_episodes(book_id)
