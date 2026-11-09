-- =============================================================================
-- Bucksy Complete Database Setup & Data Migration Script for Supabase PostgreSQL
-- =============================================================================

-- 1. Create Tables
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    ip_address TEXT,
    attempted_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    amount REAL NOT NULL CHECK(amount > 0),
    method TEXT NOT NULL DEFAULT 'Cash',
    txn_date TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS people (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS khata_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK(direction IN ('given','received','borrowed','repaid')),
    amount REAL NOT NULL CHECK(amount > 0),
    entry_date TEXT NOT NULL,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    goal_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    product_model TEXT DEFAULT '',
    price REAL NOT NULL CHECK(price > 0),
    extra_costs REAL NOT NULL DEFAULT 0 CHECK(extra_costs >= 0),
    current_savings REAL NOT NULL DEFAULT 0 CHECK(current_savings >= 0),
    saving_amount REAL NOT NULL CHECK(saving_amount > 0),
    saving_frequency TEXT NOT NULL DEFAULT 'daily' CHECK(saving_frequency IN ('daily','weekly','monthly')),
    priority TEXT NOT NULL DEFAULT 'Medium' CHECK(priority IN ('High','Medium','Low')),
    product_source TEXT DEFAULT '',
    price_checked_at TEXT DEFAULT '',
    target_date TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','achieved','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_reset_token_hash ON password_reset_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_login_attempts_filter ON login_attempts(email, attempted_at);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_people_user ON people(user_id);
CREATE INDEX IF NOT EXISTS idx_khata_user ON khata_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id);

-- 3. Compatibility Function for SQLite strftime in PostgreSQL
CREATE OR REPLACE FUNCTION strftime(format text, val text)
RETURNS text AS $$
BEGIN
    RETURN SUBSTRING(val FROM 1 FOR 7);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin INTEGER NOT NULL DEFAULT 0;

-- 4. Migrate Data from bucksy.db
-- Insert Users
INSERT INTO users (id, full_name, email, password_hash, is_admin, created_at, updated_at) VALUES 
(57, 'Yogi Morampudi', 'yogimorampudi1122@gmail.com', 'scrypt:32768:8:1$Dvf3OY5RvfZ4OgIW$6c71d525303b7f5449e4e6a15375cadec1a9cd3b5db110134db5d5b088d48914f26c6846c509da9c8683c760ed788b34c4fff8b87e7b69eebb90762cfb91bc1d', 1, '2026-10-26T04:03:43.143640', '2026-10-26T04:03:43.143640'),
(99, 'Durgesh Kashyap', 'drsdurgeshkashyap@gmail.com', 'scrypt:32768:8:1$3f6NxbywtZBu2MMu$a2e873307e70382fd3c99126ba13abbc29812480859f0565bc155800ae3d14620c364af341bbba0a9174acc35ef8f2fe5436b0ef1be7d0bf58f379a67b235f88', 0, '2026-10-26T21:27:19.445920', '2026-10-26T21:27:19.445920'),
(1001, 'Test User', 'testuser@bucksy.local', 'scrypt:32768:8:1$uZimrRj0BPYuRwv2$730ef3811bdf2bbdc15b067493d8686ff5c2a98662edc5d07abc5065758acb1e1188481d893b1c8a229f8a514b016b5b7a216375ed0ea68729237f759c9dfe0e', 0, '2026-10-27T20:39:44.639631', '2026-10-27T20:39:44.639671')
ON CONFLICT (id) DO UPDATE SET is_admin = EXCLUDED.is_admin;, 'scrypt:32768:8:1$Dvf3OY5RvfZ4OgIW$6c71d525303b7f5449e4e6a15375cadec1a9cd3b5db110134db5d5b088d48914f26c6846c509da9c8683c760ed788b34c4fff8b87e7b69eebb90762cfb91bc1d', '2026-10-26T04:03:43.143640', '2026-10-26T04:03:43.143640'),
(99, 'Durgesh Kashyap', 'drsdurgeshkashyap@gmail.com', 'scrypt:32768:8:1$3f6NxbywtZBu2MMu$a2e873307e70382fd3c99126ba13abbc29812480859f0565bc155800ae3d14620c364af341bbba0a9174acc35ef8f2fe5436b0ef1be7d0bf58f379a67b235f88', '2026-10-26T21:27:19.445920', '2026-10-26T21:27:19.445920'),
(1001, 'Test User', 'testuser@bucksy.local', 'scrypt:32768:8:1$uZimrRj0BPYuRwv2$730ef3811bdf2bbdc15b067493d8686ff5c2a98662edc5d07abc5065758acb1e1188481d893b1c8a229f8a514b016b5b7a216375ed0ea68729237f759c9dfe0e', '2026-10-27T20:39:44.639631', '2026-10-27T20:39:44.639671')
ON CONFLICT (id) DO NOTHING;

-- Insert Transactions
INSERT INTO transactions (id, kind, title, category, amount, method, txn_date, notes, user_id) VALUES 
(1, 'income', 'Salary', 'Bills', 1000.0, 'UPI', '2026-10-26', '', 57),
(2, 'expense', 'Salary', 'Bills', 600.0, 'UPI', '2026-10-26', '', 57)
ON CONFLICT (id) DO NOTHING;

-- Insert Password Reset Tokens
INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, used_at, created_at) VALUES 
(41, 99, 'eb2fc9913c7c28260abad1693d4efbf221c0f51c89d3761781a745459444cd11', '2026-10-26T21:57:39.451980', NULL, '2026-10-26T21:27:39.452014'),
(42, 99, 'ea768f5c1583f18c0d770129d5833287efbb562acd6aed482fe6623f6becb833', '2026-10-26T21:57:42.701611', NULL, '2026-10-26T21:27:42.701637'),
(43, 99, '09f32b06303f8aa10dbff6c33cdfa055718b667c05387e69e9827e14a22c0db3', '2026-10-26T21:57:48.599345', NULL, '2026-10-26T21:27:48.599372'),
(44, 99, 'e00b8452429a85c7bb83c1f7578013c6d737c8381db9b4cb3d7f72e103f9593e', '2026-10-26T21:58:09.673084', NULL, '2026-10-26T21:28:09.673136'),
(45, 99, '90e4b2ad28f4bc181c230c9e7a753dcfce31c28d80a44f33477e60ae1f117365', '2026-10-26T21:58:49.867056', NULL, '2026-10-26T21:28:49.867083')
ON CONFLICT (id) DO NOTHING;

-- 5. Sync Auto-increment Primary Key Sequences
SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1));
SELECT setval('transactions_id_seq', COALESCE((SELECT MAX(id) FROM transactions), 1));
SELECT setval('password_reset_tokens_id_seq', COALESCE((SELECT MAX(id) FROM password_reset_tokens), 1));
SELECT setval('people_id_seq', COALESCE((SELECT MAX(id) FROM people), 1));
SELECT setval('khata_entries_id_seq', COALESCE((SELECT MAX(id) FROM khata_entries), 1));
SELECT setval('goals_id_seq', COALESCE((SELECT MAX(id) FROM goals), 1));
SELECT setval('login_attempts_id_seq', COALESCE((SELECT MAX(id) FROM login_attempts), 1));

