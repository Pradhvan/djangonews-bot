CREATE TABLE IF NOT EXISTS volunteers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    reminder_date DATE NOT NULL,
    is_taken BOOLEAN DEFAULT FALSE,
    due_date DATE NOT NULL,
    email TEXT,
    status TEXT DEFAULT 'pending',
    timezone TEXT DEFAULT 'UTC'
);