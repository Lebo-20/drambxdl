import os
import re
import logging
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

class Database:
    def __init__(self):
        self.url = DATABASE_URL
        self._create_tables()

    def _get_connection(self):
        return psycopg2.connect(self.url, sslmode='require')

    def _create_tables(self):
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Table for successful uploads
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS processed_dramas (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        normalized_title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Table for failure tracking
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS drama_failures (
                        id TEXT PRIMARY KEY,
                        failure_count INT DEFAULT 0,
                        last_failure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        permanent_skip BOOLEAN DEFAULT FALSE
                    )
                ''')
                # Index for title search
                cur.execute('''
                    CREATE INDEX IF NOT EXISTS idx_normalized_title ON processed_dramas(normalized_title)
                ''')
            conn.commit()

    def normalize_title(self, title):
        if not title: return ""
        title = title.lower()
        title = re.sub(r'\(.*?\)', '', title)
        title = re.sub(r'\[.*?\]', '', title)
        title = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title = " ".join(title.split())
        return title

    def is_processed(self, drama_id, title=None):
        """Checks if the drama is already successfully uploaded."""
        normalized = self.normalize_title(title) if title else None
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Check by ID
                    cur.execute("SELECT 1 FROM processed_dramas WHERE id = %s", (str(drama_id),))
                    if cur.fetchone(): return True
                    
                    # Check by normalized title
                    if normalized:
                        cur.execute("SELECT 1 FROM processed_dramas WHERE normalized_title = %s", (normalized,))
                        if cur.fetchone(): return True
            return False
        except Exception as e:
            logger.error(f"Error checking processed status: {e}")
            return False

    def is_skipped(self, drama_id):
        """
        Checks if the drama should be skipped due to failures.
        - 2 failures in 1 day -> skip for 24h.
        - 3+ failures -> permanent skip.
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute("SELECT * FROM drama_failures WHERE id = %s", (str(drama_id),))
                    row = cur.fetchone()
                    if not row: return False
                    
                    if row['permanent_skip']:
                        return True
                    
                    if row['failure_count'] >= 2:
                        # Check if last failure was within 24 hours
                        last_fail = row['last_failure']
                        if datetime.now() - last_fail < timedelta(hours=24):
                            return True
            return False
        except Exception as e:
            logger.error(f"Error checking skip status: {e}")
            return False

    def report_failure(self, drama_id):
        """Increments failure count and updates timing."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute("SELECT failure_count FROM drama_failures WHERE id = %s", (str(drama_id),))
                    row = cur.fetchone()
                    
                    if row:
                        new_count = row['failure_count'] + 1
                        is_permanent = new_count >= 3
                        cur.execute('''
                            UPDATE drama_failures 
                            SET failure_count = %s, last_failure = CURRENT_TIMESTAMP, permanent_skip = %s
                            WHERE id = %s
                        ''', (new_count, is_permanent, str(drama_id)))
                    else:
                        cur.execute('''
                            INSERT INTO drama_failures (id, failure_count, last_failure, permanent_skip)
                            VALUES (%s, 1, CURRENT_TIMESTAMP, FALSE)
                        ''', (str(drama_id),))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error reporting failure: {e}")
            return False

    def mark_processed(self, drama_id, title):
        """Marks a drama as successfully processed."""
        normalized = self.normalize_title(title)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO processed_dramas (id, title, normalized_title)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, normalized_title = EXCLUDED.normalized_title
                    ''', (str(drama_id), title, normalized))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking processed: {e}")
            return False

    def get_stats(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM processed_dramas")
                    total = cur.fetchone()[0]
                    cur.execute("SELECT title, created_at FROM processed_dramas ORDER BY created_at DESC LIMIT 5")
                    latest = cur.fetchall()
                    return total, latest
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return 0, []

db = Database()
