-- Migration 002: Add is_admin flag to users table
-- Run: psql $DATABASE_URL -f storage/migrations/002_add_is_admin_to_users.sql

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- After running, promote your account:
-- UPDATE users SET is_admin = TRUE WHERE email = 'your@email.com';
