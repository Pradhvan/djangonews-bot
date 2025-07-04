# Migration System

## Overview

The Django News Bot uses a numbered migration system for database changes. Each migration is a Python file with a specific structure.

## Migration Files

- `00_initial_migration.py` - Adds profile columns and indexes to volunteers table
- `01_add_cache_and_reports_tables.py` - Adds cache_entries and weekly_reports tables

## Usage

### Run all pending migrations:
```bash
python migrate.py
```

### List available migrations:
```bash
python migrate.py --list
```

### Show migration status:
```bash
python migrate.py --status
```

### Run specific migration:
```bash
python migrate.py --run 01
```

## Migration File Structure

Each migration file must have:

```python
async def check_migration_needed(conn):
    """Check if this migration is needed"""
    # Return list of changes needed
    pass

async def apply_migration(conn):
    """Apply this migration"""
    # Perform the migration
    pass

# Migration metadata
MIGRATION_ID = "XX"
MIGRATION_NAME = "migration_name"
MIGRATION_DESCRIPTION = "Description of what this migration does"
```

## Creating New Migrations

1. Create file: `migrations/XX_descriptive_name.py`
2. Use next available number (02, 03, etc.)
3. Implement required functions
4. Test with `python migrate.py --run XX`

## Safety Features

- Automatic database backup before migrations
- Migration tracking (applied_migrations table)
- Rollback-safe operations
- Confirmation prompts for destructive changes
