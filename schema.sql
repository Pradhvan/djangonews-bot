-- Django News Bot Database Schema
-- This file contains the complete database schema for fresh installations

-- Main volunteers table
CREATE TABLE IF NOT EXISTS volunteers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    reminder_date DATE NOT NULL,
    is_taken BOOLEAN DEFAULT FALSE,
    due_date DATE NOT NULL,
    email TEXT,
    status TEXT DEFAULT 'pending',
    timezone TEXT DEFAULT 'UTC',
    social_media_handle TEXT,
    preferred_reminder_time TEXT DEFAULT '09:00',
    volunteer_name TEXT
);

-- Cache entries table for storing cached data (Django welcome message, etc.)
CREATE TABLE IF NOT EXISTS cache_entries (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    commit_sha TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly reports table for storing PR summaries
CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_prs INTEGER,
    first_time_contributors_count INTEGER,
    synopsis TEXT,
    date_range_humanized TEXT,
    pr_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(start_date, end_date)
);

-- Migration tracking table
CREATE TABLE IF NOT EXISTS applied_migrations (
    migration_id TEXT PRIMARY KEY,
    migration_name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes for volunteers table
CREATE INDEX IF NOT EXISTS idx_volunteers_name ON volunteers(name);
CREATE INDEX IF NOT EXISTS idx_volunteers_due_date ON volunteers(due_date);
CREATE INDEX IF NOT EXISTS idx_volunteers_is_taken ON volunteers(is_taken);
CREATE INDEX IF NOT EXISTS idx_volunteers_name_taken ON volunteers(name, is_taken);

-- Indexes for cache_entries table
CREATE INDEX IF NOT EXISTS idx_cache_entries_key ON cache_entries(key);

-- Indexes for weekly_reports table
CREATE INDEX IF NOT EXISTS idx_weekly_reports_dates ON weekly_reports(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_weekly_reports_created ON weekly_reports(created_at);
