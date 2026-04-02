import os
import asyncio
import logging
import shutil
import tempfile
import random
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv

load_dotenv()

# Local imports
from api import (
    get_drama_detail, get_all_episodes, get_latest_dramas,
    get_dubbed_dramas, get_foryou_dramas, get_popular_search,
    get_homepage_dramas
)
from downloader import download_all_episodes
from merge import merge_episodes
from uploader import upload_drama

# Configuration
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
AUTO_CHANNEL = int(os.environ.get("AUTO_CHANNEL", ADMIN_ID))
PROCESSED_FILE = "processed.json"

# State
processed_ids = set()

def load_processed():
    global processed_ids
    if os.path.exists(PROCESSED_FILE):
        import json
        try:
            with open(PROCESSED_FILE, "r") as f:
                processed_ids = set(json.load(f))
        except:
            processed_ids = set()

def save_processed(data):
    import json
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(data), f)

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot State
class BotState:
    is_auto_running = True
    is_processing = False

# Initialize client placeholder
client = None

def get_panel_buttons():
    status_text = "🟢 RUNNING" if BotState.is_auto_running else "🔴 STOPPED"
    return [
        [Button.inline("▶️ Start Auto", b"start_auto"), Button.inline("⏹ Stop Auto", b"stop_auto")],
        [Button.inline(f"📊 Status: {status_text}", b"status")]
    ]

# Event Handlers (Will be registered on main initialization)
async def setup_handlers(c):
    @c.on(events.NewMessage(pattern='/panel'))
    async def panel_handler(event):
        if event.chat_id != ADMIN_ID: return
        await event.reply("🎛 **Dramabox Control Panel**", buttons=get_panel_buttons())

    @c.on(events.CallbackQuery())
    async def callback_handler(event):
        if event.sender_id != ADMIN_ID: return
        data = event.data
        if data == b"start_auto":
            BotState.is_auto_running = True
            await event.answer("Auto-mode started!")
            await event.edit("🎛 **Dramabox Control Panel**", buttons=get_panel_buttons())
        elif data == b"stop_auto":
            BotState.is_auto_running = False
            await event.answer("Auto-mode stopped!")
            await event.edit("🎛 **Dramabox Control Panel**", buttons=get_panel_buttons())
        elif data == b"status":
            await event.answer(f"Status: {'Running' if BotState.is_auto_running else 'Stopped'}")
            await event.edit("🎛 **Dramabox Control Panel**", buttons=get_panel_buttons())

    @c.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        await event.reply("Welcome to Dramabox Downloader Bot! 🎉\n\nGunakan perintah `/download {bookId}` untuk mulai.")

    @c.on(events.NewMessage(pattern=r'/download (\d+)'))
    async def download_handler(event):
        if event.chat_id != ADMIN_ID: return
        if BotState.is_processing:
            await event.reply("⚠️ Sedang memproses drama lain. Tunggu hingga selesai.")
            return
            
        book_id = event.pattern_match.group(1)
        detail = await get_drama_detail(book_id)
        if not detail:
            await event.reply(f"❌ Gagal mendapatkan detail drama `{book_id}`.")
            return
            
        episodes = await get_all_episodes(book_id)
        if not episodes:
            await event.reply(f"❌ Drama `{book_id}` tidak memiliki episode.")
            return
            
        title = detail.get("title") or detail.get("bookName") or f"Drama_{book_id}"
        status_msg = await event.reply(f"🎬 Drama: **{title}**\n📽 Episodes: {len(episodes)}\n⏳ Memproses...")
        
        BotState.is_processing = True
        processed_ids.add(book_id)
        save_processed(processed_ids)
        
        await process_drama_full(book_id, event.chat_id, status_msg)
        BotState.is_processing = False

async def process_drama_full(book_id, chat_id, status_msg=None):
    detail = await get_drama_detail(book_id)
    episodes = await get_all_episodes(book_id)
    if not detail or not episodes:
        if status_msg: await status_msg.edit(f"❌ Data {book_id} tidak ditemukan.")
        return False

    title = detail.get("title") or detail.get("bookName") or f"Drama_{book_id}"
    description = detail.get("intro") or detail.get("introduction") or "No description."
    poster = detail.get("cover") or detail.get("coverWap") or ""
    
    temp_dir = tempfile.mkdtemp(prefix=f"dramabox_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...")
        success = await download_all_episodes(episodes, video_dir)
        if not success:
            if status_msg: await status_msg.edit("❌ Download Gagal.")
            return False

        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        merge_success = merge_episodes(video_dir, output_video_path)
        if not merge_success:
            if status_msg: await status_msg.edit("❌ Merge Gagal.")
            return False

        upload_success = await upload_drama(client, chat_id, title, description, poster, output_video_path)
        if upload_success:
            if status_msg: await status_msg.delete()
            return True
        else:
            if status_msg: await status_msg.edit("❌ Upload Gagal.")
            return False
    except Exception as e:
        logger.error(f"Error processing {book_id}: {e}")
        return False
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

async def auto_mode_loop():
    logger.info("🚀 Auto-Mode Scanner Started.")
    is_initial_run = True
    while True:
        if not BotState.is_auto_running:
            await asyncio.sleep(10)
            continue
        try:
            interval = 5 if is_initial_run else 15
            logger.info("🔍 Scanning for new dramas...")
            
            queue = []
            
            # Categories
            latest = await get_latest_dramas() or []
            queue.extend([(d, "LATEST") for d in latest])
            
            dubbed = await get_dubbed_dramas() or []
            queue.extend([(d, "DUBBED") for d in dubbed])
            
            foryou = await get_foryou_dramas() or []
            queue.extend([(d, "FOR YOU") for d in foryou])
            
            home = await get_homepage_dramas() or []
            queue.extend([(d, "HOMEPAGE") for d in home])
            
            popular = await get_popular_search() or []
            if isinstance(popular, list):
                queue.extend([(d, "POPULAR") for d in popular])
            elif popular:
                queue.append((popular, "POPULAR"))
            
            new_queue = []
            for d, cat in queue:
                bid = str(d.get("bookId") or d.get("id") or "")
                if bid and bid not in processed_ids:
                    new_queue.append((d, cat))
            
            if not new_queue:
                logger.info("😴 No new dramas.")
            else:
                for drama, cat in new_queue:
                    if not BotState.is_auto_running: break
                    bid = str(drama.get("bookId") or drama.get("id") or "")
                    processed_ids.add(bid)
                    save_processed(processed_ids)
                    
                    title = drama.get("title") or drama.get("bookName") or "Unknown"
                    logger.info(f"✨ [{cat}] New: {title} ({bid})")
                    
                    try: 
                        await client.send_message(ADMIN_ID, f"🆕 **Auto-Detected!**\n🎬 `[{cat}] {title}`\n🆔 `{bid}`")
                    except: pass
                    
                    BotState.is_processing = True
                    await process_drama_full(bid, AUTO_CHANNEL)
                    BotState.is_processing = False
                    await asyncio.sleep(10)
            
            is_initial_run = False
            for _ in range(interval * 60):
                if not BotState.is_auto_running: break
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in auto loop: {e}")
            await asyncio.sleep(60)

async def start_bot():
    global client
    logger.info("Initializing Dramabox Bot...")
    load_processed()
    
    client = TelegramClient('dramabox_bot', API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)
    logger.info("Bot is active.")
    
    await setup_handlers(client)
    
    # Start auto loop
    asyncio.create_task(auto_mode_loop())
    
    # Keeping the client running
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
