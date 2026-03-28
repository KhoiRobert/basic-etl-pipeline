# Basic CSV → PostgreSQL ETL Pipeline

A Python ETL that reads job postings from CSV with pandas, transforms salary and location fields, normalizes job titles into role categories, and loads results into PostgreSQL with SQLAlchemy. Docker Compose runs PostgreSQL 16 and pgAdmin locally.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Docker Compose)
- Python 3.11+ (recommended)

## Setup

1. Clone this repository and `cd` into the project root (required so imports like `config` and `etl` resolve).
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy the environment template: `cp .env.example .env`  
   Adjust values if needed. **Do not commit `.env`**—it is listed in `.gitignore`.
4. Start PostgreSQL and pgAdmin:
   ```bash
   docker compose up -d
   ```
5. Use `DB_HOST=localhost` in `.env` when you run `main.py` on the host (not inside a container).

## How to run

```bash
python main.py data/raw/data.csv
```

Optional arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| `filepath` | `data.csv` (project root) | Path to the input CSV. |
| `--table` | `records` | Table for the main job rows. |
| `--locations-table` | `job_locations` | Table for job ↔ location rows. |

Example:

```bash
python main.py data/raw/data.csv --table records --locations-table job_locations
```

The CLI prints extract/transform stats and a summary such as:  
`rows extracted: N / loaded: N records, M job_locations`.

Logging uses **INFO** to the terminal. For Postgres container logs:

```bash
docker compose logs -f postgres
```

## Transform pipeline

`etl.transform.transform` runs after extract:

1. **Salary** (`etl/transform/salary.py`): parses the `salary` column into `min_salary`, `max_salary`, `salary_unit` (VND / USD).
2. **Job title** (`etl/transform/job_title.py`): adds `job_role_category` (e.g. Software Development, QA & Testing) from keyword rules on `job_title`.
3. **Address** (`etl/transform/address.py`): expands `address` into one row per `(city, district)` in `job_locations`, keyed by `job_id`. Colon-separated regions and comma-separated districts under a city are supported.

The main dataframe gets a **`job_id`** column (stable row index). Processed CSVs are written under `data/processed/`:

| File | Contents |
|------|----------|
| `salary_cleaned.csv` | Full transformed job table (includes `job_role_category`, not separate city/district columns). |
| `job_locations.csv` | `job_id`, `sort_order`, `city`, `district`. |

## Inspecting the database

**pgAdmin:** open [http://localhost:8080](http://localhost:8080) and sign in with `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` from `.env`. Register a server: host `localhost`, port from `DB_PORT`, database `DB_NAME`, user/password from `.env`.

**psql inside the Postgres container:**

```bash
docker compose exec postgres psql -U "$DB_USER" -d "$DB_NAME"
```

Inside `psql`, use `\dt` to list tables. Join locations with jobs:

```sql
SELECT r.job_title, l.city, l.district
FROM records r
LEFT JOIN job_locations l ON r.job_id = l.job_id
LIMIT 20;
```

(`records` columns follow your CSV; `config/schema.sql` seeds an example table on **first** volume init—`pandas.to_sql(..., if_exists="replace")` overwrites with the current DataFrame shape.)

## Scheduled runs

- **`scripts/run_pipeline.sh`**: runs `main.py` from the repo root (prefers `.venv/bin/python`, default CSV `data/raw/data.csv`).
- **`scripts/crontab.example`**: example cron line with logging to `logs/`.
- **`.github/workflows/etl-scheduled.yml`**: daily schedule (UTC) and manual **workflow_dispatch**. Configure repository secrets `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` so the runner can reach PostgreSQL (a public host or tunnel; `localhost` will not work from GitHub-hosted runners).

## Project layout

| Path | Purpose |
|------|---------|
| `data/raw/` | Source CSV inputs. |
| `data/processed/` | Outputs from transform (`salary_cleaned.csv`, `job_locations.csv`). |
| `data/failed/` | Reserved for quarantined rows (optional). |
| `config/settings.py` | Loads `.env`, `get_engine()`, data directory paths. |
| `config/schema.sql` | Mounted into Postgres init on first volume creation. |
| `etl/extract/` | CSV read (UTF-8 with Latin-1 fallback, stripped column names). |
| `etl/transform/` | Salary parsing, address → locations, job title categories. |
| `etl/load/` | `pandas.to_sql` with `if_exists="replace"`. |
| `main.py` | CLI: extract → transform → load (two tables). |
| `scripts/` | Helper shell script and cron example for scheduling. |

## Troubleshooting

| Issue | What to check |
|--------|----------------|
| `No module named 'config'` | Run `python main.py` from the project root directory. |
| Connection refused / cannot connect | `docker compose ps`; Postgres must be up; `DB_HOST` / `DB_PORT` must match how you reach the container from the host. |
| Password authentication failed | Another Postgres may use the same port, or `.env` does not match the container’s `POSTGRES_*` credentials. Stop conflicting services or change the host port in `.env` and in `docker compose` port mapping. |
