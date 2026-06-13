-- Users
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Groups
CREATE TABLE IF NOT EXISTS expense_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    currency TEXT DEFAULT 'INR',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

-- Group memberships with join/leave dates
CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    joined_at TEXT NOT NULL,
    left_at TEXT,
    UNIQUE(group_id, user_id, joined_at)
);

-- Expenses
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'INR',
    amount_inr REAL NOT NULL,  -- always stored in INR after conversion
    exchange_rate REAL DEFAULT 1.0,
    split_type TEXT NOT NULL CHECK(split_type IN ('equal','exact','percentage','share')),
    paid_by INTEGER REFERENCES users(id),
    expense_date TEXT NOT NULL,
    category TEXT,
    notes TEXT,
    is_settlement INTEGER DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    import_row INTEGER  -- for tracing CSV import
);

-- Expense splits (who owes what)
CREATE TABLE IF NOT EXISTS expense_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER REFERENCES expenses(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    amount_inr REAL NOT NULL,
    share_ratio REAL  -- for percentage/share splits
);

-- Settlements / payments
CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id),
    paid_by INTEGER REFERENCES users(id),
    paid_to INTEGER REFERENCES users(id),
    amount_inr REAL NOT NULL,
    settled_at TEXT NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Import reports
CREATE TABLE IF NOT EXISTS import_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER REFERENCES expense_groups(id),
    filename TEXT,
    imported_at TEXT DEFAULT (datetime('now')),
    total_rows INTEGER,
    imported_rows INTEGER,
    skipped_rows INTEGER,
    report_json TEXT  -- full anomaly log as JSON
);
