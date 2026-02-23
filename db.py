import os
import logging
import psycopg2

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def get_db_connection():
    """
    Returns a new PostgreSQL database connection using environment variables:
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT
    """

    # Prefer IPv4 loopback to avoid ::1 (IPv6) surprises on Windows
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = int(os.getenv("DB_PORT", "5432"))

    database = os.getenv("DB_NAME", "liceo_db")
    user = os.getenv("DB_USER", "liceo_db")
    password = os.getenv("DB_PASSWORD", "liceo123")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=database,   # dbname is standard param
            user=user,
            password=password,
        )
        return conn

    except psycopg2.OperationalError as e:
        logger.error(
            "DB connection failed. Check DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT. "
            "Using host=%s port=%s db=%s user=%s",
            host, port, database, user
        )
        raise

    except Exception:
        logger.exception("Unexpected error connecting to DB")
        raise


def is_branch_active(branch_id):
    """
    Returns True if branch status is 'active' (or branch does not exist),
    False if status is anything else (e.g. 'inactive').
    """
    if not branch_id:
        return True

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM branches WHERE branch_id = %s", (branch_id,))
        row = cur.fetchone()
        if not row:
            return True
        status = row[0]
        return str(status or "").strip().lower() == "active"
    except Exception:
        logger.exception("Failed to check branch status")
        return True
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()
