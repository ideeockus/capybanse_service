CREATE_RESONANSE_EVENTS_TABLE = '''
CREATE TABLE IF NOT EXISTS resonanse_events (
    id UUID PRIMARY KEY,
     title TEXT NOT NULL,
     description TEXT,

     datetime_from TIMESTAMP NOT NULL,
     datetime_to TIMESTAMP,
     city TEXT,

     venue_title TEXT,
     venue_address TEXT,
     venue_lat FLOAT8,
     venue_lon FLOAT8,

     image_url TEXT,
     local_image_path TEXT,

     price_price FLOAT8,
     price_currency VARCHAR(255),

     tags TEXT[],
     contact TEXT,

     service_id TEXT NOT NULL UNIQUE,
     service_type TEXT,
     service_data JSONB
);
'''

CREATE_RESONANSE_USERS_TABLE = '''
CREATE TABLE IF NOT EXISTS resonanse_users (
    -- base data
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE,

    -- user data
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    city TEXT,
    description TEXT,

    headline TEXT,
    goals TEXT,
    interests TEXT,
    language TEXT,
    age SMALLINT,
    education TEXT,

    hobby TEXT,
    music TEXT,
    sport TEXT,
    books TEXT,
    food TEXT,
    worldview TEXT,

    -- contacts data
    email TEXT,
    phone TEXT,
    tg_username TEXT,
    tg_user_id BIGINT,
    instagram TEXT,

    -- auth data
    password_hash varchar(1023),

    -- other
    user_type INT NOT NULL
);
'''

CREATE_USERS_INTERACTION_TABLE = '''
CREATE TABLE IF NOT EXISTS users_interactions (
    user_id UInt64,
    event_id UUID,
    interaction_type String,
    interaction_dt DateTime
)
ENGINE MergeTree
ORDER BY interaction_dt;
'''

CREATE_GIVEN_RECOMMENDATIONS_TABLE = '''
CREATE TABLE IF NOT EXISTS given_recommendations (
    user_id UInt64,
    recommended_events Array(Tuple(event_id UUID, subsystem_kind String, score Float32)),
    recommendation_dt DateTime
)
ENGINE MergeTree
ORDER BY recommendation_dt;
'''


