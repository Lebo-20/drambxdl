import sqlite3
import re
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="dramabox.db"):
        self.db_path = db_path
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processed_dramas (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    normalized_title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_normalized_title ON processed_dramas(normalized_title)
            ''')

    def normalize_title(self, title):
        if not title: return ""
        # Remove common junk from titles
        title = title.lower()
        # Remove (Sulih Suara), (Dubbed), etc.
        title = re.sub(r'\(.*?\)', '', title)
        title = re.sub(r'\[.*?\]', '', title)
        # Remove special characters
        title = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        # Normalize whitespace
        title = " ".join(title.split())
        return title

    def is_processed(self, drama_id, title=None):
        normalized = self.normalize_title(title) if title else None
        with sqlite3.connect(self.db_path) as conn:
            # Check by ID
            if drama_id:
                res = conn.execute("SELECT 1 FROM processed_dramas WHERE id = ?", (str(drama_id),)).fetchone()
                if res: return True
            # Check by normalized title
            if normalized:
                res = conn.execute("SELECT 1 FROM processed_dramas WHERE normalized_title = ?", (normalized,)).fetchone()
                if res: return True
        return False

    def mark_processed(self, drama_id, title):
        normalized = self.normalize_title(title)
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO processed_dramas (id, title, normalized_title) VALUES (?, ?, ?)",
                    (str(drama_id), title, normalized)
                )
            return True
        except Exception as e:
            logger.error(f"Error marking {drama_id} as processed: {e}")
            return False

db = Database()
