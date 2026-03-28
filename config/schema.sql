-- Initial schema for the ETL pipeline.
-- Mounted into Postgres on first volume creation only.
-- NOTE: pandas to_sql(if_exists="replace") recreates tables at runtime,
--       so this DDL is authoritative documentation of the expected shape.

CREATE TABLE IF NOT EXISTS records (
    job_id          TEXT PRIMARY KEY,
    created_date    TEXT,
    job_title       TEXT,
    company         TEXT,
    salary          TEXT,
    address         TEXT,
    time            TEXT,
    link_description TEXT,
    min_salary      BIGINT,
    max_salary      BIGINT,
    salary_unit     TEXT,
    job_role_category TEXT
);

CREATE TABLE IF NOT EXISTS job_locations (
    id          SERIAL PRIMARY KEY,
    job_id      TEXT NOT NULL REFERENCES records(job_id) ON DELETE CASCADE,
    sort_order  INT  NOT NULL,
    city        TEXT,
    district    TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_locations_job_id ON job_locations(job_id);
CREATE INDEX IF NOT EXISTS idx_records_job_role     ON records(job_role_category);
CREATE INDEX IF NOT EXISTS idx_records_salary_unit  ON records(salary_unit);
