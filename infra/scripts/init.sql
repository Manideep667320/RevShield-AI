-- Revenue Recovery Engine — Database Initialization
-- Runs once on first PostgreSQL container start

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for fuzzy search on audit logs
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Ensure the DB is set to UTC
SET timezone = 'UTC';
