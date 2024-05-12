CREATE_RESONANSE_EVENTS_TABLE = '''
CREATE TABLE IF NOT EXISTS resonanse_events (
    id UUID PRIMARY KEY,
     title TEXT NOT NULL,
     description TEXT,

     datetime_from TIMESTAMP NOT NULL,
     datetime_to TIMESTAMP,
     city TEXT NOT NULL,

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