CREATE TABLE IF NOT EXISTS records (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    name TEXT,
    email TEXT,
    status TEXT,
    amount NUMERIC,
    source TEXT
);
