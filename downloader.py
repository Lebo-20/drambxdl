import os
import asyncio
import logging

logger = logging.getLogger(__name__)

async def download_file(url: str, path: str, ep_num: str):
    """Downloads a file using FFmpeg to handle both direct MP4 and HLS streams."""
    try:
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
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg download failed for episode {ep_num}: {stderr.decode()}")
            return False
            
        return True
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
