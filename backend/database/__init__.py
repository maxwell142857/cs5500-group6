from contextlib import contextmanager
import psycopg2
from psycopg2.extras import DictCursor

from config import DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT

@contextmanager
def get_db_connection():
    """Get a PostgreSQL connection with automatic closing"""
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_db_cursor(conn):
    """Get a cursor with automatic closing"""
    cursor = conn.cursor(cursor_factory=DictCursor)
    try:
        yield cursor
    finally:
        cursor.close()