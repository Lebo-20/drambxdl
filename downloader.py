import os
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

async def check_is_hls(url: str) -> bool:
    """Checks if a URL points to an HLS playlist by inspecting the content."""
    # Fast path: obvious extension
    if ".m3u8" in url.split('?')[0]:
        return True
        
    try:
        # Inspect headers or first few bytes
        async with httpx.AsyncClient(verify=False) as client:
            # We use GET with Range to only fetch the first few bytes
            response = await client.get(url, headers={"Range": "bytes=0-100"}, timeout=5.0)
            content = response.text
            if "#EXTM3U" in content:
                return True
    except Exception as e:
        logger.debug(f"HLS detection failed for {url}, assuming non-HLS: {e}")
        
    return False

async def validate_mp4(path: str) -> bool:
    """Checks if a file is a valid MP4 using ffprobe."""
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        return False
        
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0 and stdout.decode().strip():
            return True
    except Exception:
        pass
        
    return False

async def download_file(url: str, path: str, ep_num: str):
    """Downloads a file using aria2c for direct files or FFmpeg for HLS streams, with fallback."""
    try:
        is_hls = await check_is_hls(url)
        
        async def run_download(hls_mode: bool):
            if hls_mode:
                command = [
                    "ffmpeg", "-y",
                    "-loglevel", "error",
                    "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                    "-allowed_extensions", "ALL",
                    "-i", url,
                    "-c", "copy",
                    "-bsf:a", "aac_adtstoasc",
                    path
                ]
            else:
                command = [
                    "aria2c", "--quiet=true",
                    "--max-connection-per-server=16",
                    "--split=16",
                    "--min-split-size=1M",
                    "--dir=" + os.path.dirname(path),
                    "--out=" + os.path.basename(path),
                    "--allow-overwrite=true",
                    url
                ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0, stderr.decode()

        # First attempt
        success, err = await run_download(is_hls)
        
        if success:
            # Validate output
            if await validate_mp4(path):
                return True
            else:
                logger.warning(f"Validation failed for episode {ep_num}. Invalid data or missing moov atom.")
                success = False

        if not success:
            if not is_hls:
                logger.info(f"Retrying episode {ep_num} as HLS stream (fallback)...")
                # Remove invalid file if exists
                if os.path.exists(path):
                    os.remove(path)
                # Fallback: force HLS mode
                success_fb, err_fb = await run_download(True)
                if success_fb and await validate_mp4(path):
                    return True
                else:
                    logger.error(f"Fallback HLS download failed for episode {ep_num}: {err_fb}")
            else:
                logger.error(f"HLS download failed for episode {ep_num}: {err}")
                
        return False
        
    except Exception as e:
        logger.error(f"Failed to download {ep_num} from {url}: {e}")
        return False

async def download_all_episodes(episodes, download_dir: str, semaphore_count: int = 3):
    """
    Downloads all episodes concurrently using FFmpeg.
    """
    os.makedirs(download_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(semaphore_count)

    async def limited_download(ep):
        async with semaphore:
            ep_val = ep.get('chapterIndex') or ep.get('episode') or 'unk'
            ep_num = str(ep_val).zfill(3)
            filename = f"episode_{ep_num}.mp4"
            filepath = os.path.join(download_dir, filename)
            
            # Select URL
            url = ep.get('videoUrl') or ep.get('1080p') or ep.get('720p') or ep.get('url')
            
            if not url:
                videos = ep.get('videos', [])
                if isinstance(videos, list) and videos:
                    url = videos[0].get('url')

            if not url:
                logger.error(f"No URL found for episode {ep_num}")
                return False
                
            success = await download_file(url, filepath, ep_num)
            if success:
                logger.info(f"Successfully downloaded {filename}")
            return success

    results = await asyncio.gather(*(limited_download(ep) for ep in episodes))
    return all(results)
