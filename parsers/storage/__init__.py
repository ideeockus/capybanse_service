import psycopg

from parsers.config import POSTGRES_DB
from parsers.config import POSTGRES_HOST
from parsers.config import POSTGRES_PASSWORD
from parsers.config import POSTGRES_PORT
from parsers.config import POSTGRES_USER
from common.utils import get_logger

logger = get_logger('storage')

"""
docs: 
psycopg3 https://www.psycopg.org/psycopg3/docs/

"""

CREATE_PARSERS_STATE_TABLE = '''
CREATE TABLE IF NOT EXISTS parsers_state (
     key VARCHAR(255) PRIMARY KEY,
     value VARCHAR(255) NOT NULL
)
'''

DB_URL = f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'


def init_db():
    logger.info('init db')
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_PARSERS_STATE_TABLE)


def set_state(key: str, value: str):
    logger.info('set_state %s to %s', key, value)
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO parsers_state (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                """,
                (key, value)
            )


def get_state(key: str) -> str | None:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            value = cur.execute(
                "SELECT value FROM parsers_state WHERE key=(%s)",
                (key,),
            ).fetchone()

            if value is not None:
                return value[0]


# init table
init_db()
