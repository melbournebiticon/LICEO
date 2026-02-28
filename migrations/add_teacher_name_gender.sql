-- Run this in pgAdmin (liceo_db, as postgres superuser)

-- 1. Add full_name and gender columns to users
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS full_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS gender    VARCHAR(10);   -- 'male' or 'female'

-- 2. Give the app user access (if needed)
GRANT ALL PRIVILEGES ON TABLE users TO liceo_db;
