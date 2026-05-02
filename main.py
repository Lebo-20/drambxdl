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
    get_homepage_dramas, search_dramas
)
from downloader import download_all_episodes
from merge import merge_episodes
from uploader import upload_drama
from database import db

# Configuration
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
AUTO_CHANNEL = int(os.environ.get("AUTO_CHANNEL", ADMIN_ID))
TOPIC_ID = os.environ.get("TOPIC_ID")
TOPIC_ID = int(TOPIC_ID) if TOPIC_ID else None

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot State
class BotState:
    is_auto_running = True
    is_processing = False
    processing_type = None # "auto" or "manual"
    current_task = None    # Store the current running task
    is_paused_for_manual = False

# Initialize client placeholder
client = None

async def interrupt_auto_if_running():
    """Interrupts auto process if it's currently running."""
    if BotState.is_processing and BotState.processing_type == "auto" and BotState.current_task:
        logger.info("⚠️ Interrupting auto process for manual command...")
        BotState.current_task.cancel()
        try:
            await BotState.current_task
        except asyncio.CancelledError:
            logger.info("✅ Auto process cancelled successfully.")
        except Exception as e:
            logger.error(f"Error while cancelling auto process: {e}")
        finally:
            BotState.is_processing = False
            BotState.processing_type = None
            BotState.current_task = None

async def start_manual_process():
    """Pauses auto mode and interrupts any active auto task."""
    if BotState.is_auto_running:
        logger.info("⏸ Pausing auto mode for manual task...")
        BotState.is_auto_running = False
        BotState.is_paused_for_manual = True
    
    await interrupt_auto_if_running()
    
    # Wait a bit to ensure everything is settled
    await asyncio.sleep(1)

async def end_manual_process():
    """Resumes auto mode if it was paused."""
    if BotState.is_paused_for_manual:
        logger.info("▶️ Resuming auto mode after manual task...")
        BotState.is_auto_running = True
        BotState.is_paused_for_manual = False

def get_panel_buttons():
    status_text = "🟢 RUNNING" if BotState.is_auto_running else "🔴 STOPPED"
    return [
        [Button.inline("▶️ Start Auto", b"start_auto"), Button.inline("⏹ Stop Auto", b"stop_auto")],
        [Button.inline(f"📊 Status: {status_text}", b"status")],
        [Button.inline("📂 Browse Content", b"menu_main")]
    ]

def get_category_buttons():
    return [
        [Button.inline("❤️ For You", b"cat_foryou"), Button.inline("🆕 Latest", b"cat_latest")],
        [Button.inline("🎙 Dubbed", b"cat_dubbed"), Button.inline("🏠 Discovery", b"cat_home")],
        [Button.inline("🔙 Back to Panel", b"menu_back")]
    ]

# Event Handlers
async def setup_handlers(c):
    @c.on(events.NewMessage(pattern='/dramabox panel'))
    async def panel_handler(event):
        if event.chat_id != ADMIN_ID: return
        await event.reply("🎛 **Dramabox Control Panel**\nControl the automation and browse content.", buttons=get_panel_buttons())

    @c.on(events.NewMessage(pattern='/dramabox menu'))
    async def menu_handler(event):
        if event.chat_id != ADMIN_ID: return
        await event.reply("📂 **Pilih Kategori Konten**\nAmbil konten terbaru dari Dramabox:", buttons=get_category_buttons())

    @c.on(events.NewMessage(pattern=r'/dramabox cari (.+)'))
    async def search_handler(event):
        if event.chat_id != ADMIN_ID: return
        query = event.pattern_match.group(1)
        
        # Stop auto before searching if needed (user might just be searching, but usually search leads to download)
        # But let's only stop when download starts to be less intrusive.
        # Actually, user said "cari / download dan auto", so maybe search should also stop auto?
        # Let's stick to stop when download starts for better UX, or stop now as requested.
        await start_manual_process()
        
        wait = await event.reply(f"🔍 Searching for `{query}`...")
        
        try:
            results = await search_dramas(query)
            if not results:
                await wait.edit(f"❌ No results found for `{query}`.")
                await end_manual_process()
                return
                
            text = f"🔍 **Search Results for:** `{query}`\n\n"
            buttons = []
            for i, d in enumerate(results[:10]):
                title = d.get("title") or d.get("bookName") or "Unknown"
                bid = d.get("bookId") or d.get("id")
                text += f"{i+1}. **{title}** (`{bid}`)\n"
                buttons.append([Button.inline(f"📥 Download: {title[:20]}...", f"dl_{bid}".encode())])
            
            await wait.edit(text, buttons=buttons)
        except Exception as e:
            await wait.edit(f"❌ Error during search: {e}")
            await end_manual_process()

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
            
        elif data == b"menu_main" or data == b"menu_back":
            await event.edit("📂 **Pilih Kategori Konten**", buttons=get_category_buttons())

        elif data.startswith(b"cat_"):
            cat = data.decode().split("_")[1]
            await event.answer(f"Fetching {cat}...")
            
            items = []
            if cat == "foryou": items = await get_foryou_dramas()
            elif cat == "latest": items = await get_latest_dramas()
            elif cat == "dubbed": items = await get_dubbed_dramas()
            elif cat == "home": items = await get_homepage_dramas()
            
            if not items:
                await event.edit(f"❌ No content found in **{cat.upper()}**.", buttons=get_category_buttons())
                return
                
            text = f"📂 **Category: {cat.upper()}**\n\n"
            buttons = []
            for i, d in enumerate(items[:8]):
                title = d.get("title") or d.get("bookName") or "Unknown"
                bid = d.get("bookId") or d.get("id")
                text += f"{i+1}. **{title}** (`{bid}`)\n"
                buttons.append([Button.inline(f"📥 Download: {title[:20]}...", f"dl_{bid}".encode())])
            
            buttons.append([Button.inline("🔙 Back", b"menu_back")])
            await event.edit(text, buttons=buttons)

        elif data.startswith(b"dl_"):
            bid = data.decode().split("_")[1]
            
            # Ensure auto is stopped and current auto task is killed
            await start_manual_process()
            
            if BotState.is_processing:
                await event.answer("⚠️ Bot is busy with another manual task!", alert=True)
                return
            
            await event.answer("Starting download...")
            status_msg = await event.respond(f"⏳ Initializing download for `{bid}`...")
            
            BotState.is_processing = True
            BotState.processing_type = "manual"
            try:
                success = await process_drama_full(bid, event.chat_id, status_msg, topic_id=None)
                # Note: Manual downloads are NOT recorded in DB as per user request
            finally:
                BotState.is_processing = False
                BotState.processing_type = None
                await end_manual_process()

    @c.on(events.NewMessage(pattern='/dramabox new'))
    async def update_command_handler(event):
        if event.chat_id != ADMIN_ID: return
        await start_manual_process()
        status_msg = await event.reply("🔄 **Starting manual update...**\nFetching all categories...")
        try:
            await perform_scan(is_manual=True, status_msg=status_msg)
        finally:
            await end_manual_process()

    @c.on(events.NewMessage(pattern='/dramabox db'))
    async def db_handler(event):
        if event.chat_id != ADMIN_ID: return
        total, latest = db.get_stats()
        text = f"📊 **Dramabox Database Statistics**\n\n"
        text += f"Total Uploaded Titles: `{total}`\n\n"
        text += "最近 (Latest 5):\n"
        for i, (title, time) in enumerate(latest):
            text += f"{i+1}. {title} ({time})\n"
        await event.reply(text)

    @c.on(events.NewMessage(pattern=r'/(start|dramabox start)'))
    async def start_handler(event):
        await event.reply("Welcome to Dramabox Downloader Bot! 🎉\n\nCommands:\n- `/dramabox panel` : Admin Control Panel\n- `/dramabox menu` : Browse Categories\n- `/dramabox cari {query}` : Search Drama\n- `/dramabox new` : Manual content scan\n- `/dramabox download {id}` : Direct Download\n- `/dramabox db` : View uploaded database")

    @c.on(events.NewMessage(pattern=r'/dramabox download (\d+)'))
    async def download_handler(event):
        if event.chat_id != ADMIN_ID: return
        
        await start_manual_process()
        
        if BotState.is_processing:
            await event.reply("⚠️ Bot is busy with another manual task.")
            return
            
        bid = event.pattern_match.group(1)
        status_msg = await event.reply(f"⏳ Memulai proses `{bid}`...")
        
        BotState.is_processing = True
        BotState.processing_type = "manual"
        try:
            await process_drama_full(bid, event.chat_id, status_msg, topic_id=None)
        finally:
            BotState.is_processing = False
            BotState.processing_type = None
            await end_manual_process()

async def process_drama_full(book_id, chat_id, status_msg=None, topic_id=None):
    detail = await get_drama_detail(book_id)
    episodes = await get_all_episodes(book_id)
    if not detail or not episodes:
        if status_msg: await status_msg.edit(f"❌ Data {book_id} tidak ditemukan.")
        return False

    title = detail.get("title") or detail.get("bookName") or f"Drama_{book_id}"
    description = detail.get("intro") or detail.get("introduction") or "No description."
    poster = detail.get("bookCover") or detail.get("cover") or detail.get("coverWap") or ""
    
    temp_dir = tempfile.mkdtemp(prefix=f"dramabox_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...\n📥 Downloading {len(episodes)} episodes...")
        success = await download_all_episodes(episodes, video_dir)
        if not success:
            if status_msg: await status_msg.edit(f"❌ Download Gagal: **{title}**\nBeberapa episode tidak dapat diunduh.")
            return False

        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...\n🔄 Merging episodes into one file...")
        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        merge_success = merge_episodes(video_dir, output_video_path)
        if not merge_success:
            if status_msg: await status_msg.edit(f"❌ Merge Gagal: **{title}**\nFile video mungkin corrupt atau tidak kompatibel.")
            return False

        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...\n📤 Uploading to Telegram...")
        upload_success = await upload_drama(client, chat_id, title, description, poster, output_video_path, topic_id=topic_id, max_retries=5)
        if upload_success:
            if status_msg: await status_msg.delete()
            return True
        else:
            if status_msg: await status_msg.edit(f"❌ Upload Gagal: **{title}**\nKoneksi terputus atau file terlalu besar.")
            return False
    except asyncio.CancelledError:
        logger.info(f"Process for {book_id} was cancelled.")
        raise
    except Exception as e:
        logger.error(f"Error processing {book_id}: {e}")
        if status_msg: await status_msg.edit(f"❌ Error: {str(e)[:100]}")
        return False
    finally:
        if os.path.exists(temp_dir): 
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

async def perform_scan(is_manual=False, status_msg=None):
    """Core scanning logic for all categories."""
    logger.info("🔍 Scanning sections for new dramas...")
    if status_msg: await status_msg.edit("🔍 **Full Scan Started...**\nChecking categories...")
    
    categories = [
        (get_latest_dramas, "LATEST"),
        (get_dubbed_dramas, "DUBBED"),
        (get_foryou_dramas, "FOR YOU"),
        (get_homepage_dramas, "HOMEPAGE"),
        (get_popular_search, "POPULAR")
    ]
    
    total_found = 0
    for func, cat_name in categories:
        if not BotState.is_auto_running and not is_manual: break
        
        try:
            items = await func()
        except Exception as e:
            logger.error(f"Error fetching {cat_name}: {e}")
            continue
            
        if not items: continue
        if not isinstance(items, list): items = [items]
        
        for item in items:
            if not BotState.is_auto_running and not is_manual: break
            
            bid = str(item.get("bookId") or item.get("id") or "")
            title = item.get("title") or item.get("bookName") or "Unknown"
            poster = item.get("bookCover") or item.get("cover") or item.get("coverWap") or ""
            
            if not bid: continue
            
            # Deduplication & Skip Logic using Database
            if db.is_processed(bid, title):
                continue
                
            if db.is_skipped(bid):
                logger.warning(f"⏩ Skipping {title} ({bid}) due to previous failures.")
                continue
                
            total_found += 1
            logger.info(f"✨ [{cat_name}] New: {title} ({bid})")
            
            # Notify Admin
            try: 
                await client.send_message(ADMIN_ID, f"🆕 **Detected!**\n🎬 `[{cat_name}] {title}`\n🆔 `{bid}`")
            except: pass
            
            # Process
            BotState.is_processing = True
            BotState.processing_type = "auto"
            
            # Wrap the process in a task so it can be cancelled
            BotState.current_task = asyncio.create_task(process_drama_full(bid, AUTO_CHANNEL, topic_id=TOPIC_ID))
            
            try:
                success = await BotState.current_task
            except asyncio.CancelledError:
                logger.warning(f"Auto-process for {bid} was cancelled mid-way.")
                break 
            except Exception as e:
                logger.error(f"Auto-process error for {bid}: {e}")
                success = False
            finally:
                BotState.is_processing = False
                BotState.processing_type = None
                BotState.current_task = None
            
            if success:
                db.mark_processed(bid, title)
                if not is_manual:
                    cooldown = 3600 # 1 Hour in seconds
                    logger.info(f"✅ Success! Auto-mode cooling down for 1 hour...")
                    try:
                        await client.send_message(ADMIN_ID, f"✅ **Berhasil Upload!**\n🎬 `{title}`\n\n💤 **Auto Cooldown:** 1 Jam.\nBot akan lanjut otomatis setelah istirahat.")
                    except: pass
                    
                    # Sleep for 1 hour, but check if auto is still running
                    for _ in range(cooldown):
                        if not BotState.is_auto_running or BotState.is_paused_for_manual:
                            break
                        await asyncio.sleep(1)
            else:
                logger.error(f"❌ Auto-process failed for {title} ({bid}). Reporting failure and stopping scan.")
                db.report_failure(bid)
                # "jika ada video yang gagal maka akan auto stop proses"
                if not is_manual:
                    return # Stop the entire scan
            
            if is_manual:
                await asyncio.sleep(5) # Short sleep for manual
            else:
                # If we are here, it means we didn't success (or cooldown was broken)
                await asyncio.sleep(15)
            
    if is_manual and status_msg:
        if total_found > 0:
            await status_msg.edit(f"✅ **Update Complete!**\nFound and processed {total_found} new dramas.")
        else:
            await status_msg.edit("😴 **Update Complete.**\nNo new dramas found.")
    
    logger.info(f"✨ Scan complete. Found {total_found} new items.")

async def auto_mode_loop():
    logger.info("🚀 Auto-Mode Scanner Started.")
    is_initial_run = True
    while True:
        if not BotState.is_auto_running:
            await asyncio.sleep(5)
            continue
        try:
            # Faster interval: 1 min if initial, 3 mins otherwise
            interval = 1 if is_initial_run else 3
            await perform_scan()
            is_initial_run = False
            
            logger.info(f"Waiting {interval} minutes for next scan...")
            # Wait for next scan
            for _ in range(interval * 60):
                if not BotState.is_auto_running: break
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in auto loop: {e}")
            await asyncio.sleep(30)

async def start_bot():
    global client
    logger.info("Initializing Dramabox Bot...")
    
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
        logger.info("Bot stopped.")
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
