import psycopg

"""
docs: 
psycopg3 https://www.psycopg.org/psycopg3/docs/

"""

CREATE_PARSERS_STATE_TABLE = '''
CREATE TABLE IF NOT EXISTS parsers_state (
     key STRING PRIMARY KEY,
     value STRING NOT NULL,
)
'''