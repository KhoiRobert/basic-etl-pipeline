# Basic CSV → PostgreSQL ETL Pipeline

A minimal Python project that reads CSV files with pandas, optionally cleans them with your own transformation code, and loads the result into PostgreSQL using SQLAlchemy. Docker Compose runs PostgreSQL 16 and pgAdmin locally so you do not need a separate database install.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Docker Compose)
- Python 3.11+ (recommended)

## Setup

1. Clone this repository and `cd` into the project root (required so `python` can import `config` and `etl`).
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy the environment template: `cp .env.example .env`  
   Adjust values if needed. **Do not commit `.env`**—it is listed in `.gitignore`. Only `.env.example` belongs in the repo.
4. Start PostgreSQL and pgAdmin:
   ```bash
   docker compose up -d
   ```
5. Ensure `DB_HOST=localhost` in `.env` when you run `main.py` on your machine (not inside Docker).

## How to run

```bash
python main.py data/raw/your_file.csv --table your_table
```

- Omit `--table` to use the default table name **`records`** (see also `config/schema.sql` for the initial DDL on first DB init).
- The CLI prints a one-line summary: `rows extracted: N / rows loaded: N`.
- Logging is at **INFO** to the terminal (timestamps included). For container logs:
  ```bash
  docker compose logs -f postgres
  ```

## Inspecting the database

**pgAdmin:** open [http://localhost:8080](http://localhost:8080) and sign in with `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` from `.env`. Register a server: host `localhost`, port from `DB_PORT`, database `DB_NAME`, user/password from `.env`.

**psql inside the Postgres container:**

```bash
docker compose exec postgres psql -U postgres -d etl_db
```

Use your actual `DB_USER` and `DB_NAME` if they differ. Inside `psql`, try `\dt` to list tables and `SELECT * FROM your_table LIMIT 20;`.

## Adding your own transformation

1. Add `etl/transform.py` with a function such as `transform(df) -> df`.
2. In `main.py`, replace the marked **TODO** block: import your function and set `clean_df = transform(raw_df)`, then remove the temporary `clean_df = raw_df` line.
3. Optionally write intermediate files under `data/processed/` using `PROCESSED_DIR` from `config.settings` (nothing writes there until you add that code).

## Project layout

| Path | Purpose |
|------|---------|
| `data/raw/` | Typical location for source CSV inputs. |
| `data/processed/` | For you to save cleaned or intermediate files when you implement transforms. |
| `data/failed/` | For quarantined or rejected rows/files (optional). |
| `config/settings.py` | Loads `.env`, `get_engine()`, and `Path` constants for data dirs. |
| `config/schema.sql` | Mounted into Postgres init; creates `records` on **first** volume init only. |
| `etl/extract.py` | CSV extract: UTF-8 with Latin-1 fallback, stripped column names. |
| `etl/load.py` | Load via `pandas.to_sql` with `if_exists="replace"`. |
| `main.py` | CLI: extract → transform placeholder → load. |

## Troubleshooting

| Issue | What to check |
|--------|----------------|
| `No module named 'config'` | Run `python main.py` from the project root directory. |
| Connection refused / cannot connect | `docker compose ps`; Postgres must be up; `DB_HOST` / `DB_PORT` must match how you reach the container from the host. |
| Password authentication failed | Another Postgres may be bound to the same port, or `.env` does not match the container’s `POSTGRES_*` credentials. Stop conflicting services or change the host port in `.env` and in `docker compose` port mapping. |
