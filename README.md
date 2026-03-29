# Basic ETL Pipeline — CSV → PostgreSQL

A production-quality Python ETL pipeline for Vietnamese IT job posting data.  
Extracts from CSV, normalises salary / address / job-title fields, and loads into PostgreSQL.

---

## Requirements & What Was Built

### Requirement 1 — Data Cleaning & Normalization

#### 1.1 Salary normalization → `min_salary`, `max_salary`, `salary_unit`

Raw salary strings come in many formats. `etl/transform/salary.py` handles all of them:

| Raw value | `min_salary` | `max_salary` | `salary_unit` |
|-----------|-------------|-------------|---------------|
| `10 - 20 triệu` | 10 000 000 | 20 000 000 | VND |
| `Trên 15 triệu` | 15 000 000 | — | VND |
| `Tới 30 triệu` | — | 30 000 000 | VND |
| `$1 500 - $2 000` | 1 500 | 2 000 | USD |
| `Thoả thuận` / `Negotiable` | — | — | — |

#### 1.2 Address parsing → `job_locations` table

Raw addresses follow patterns like `City: District` or `City: D1, D2, D3` or  
`City1: D1: City2: D2`. `etl/transform/address.py` expands each into one row per  
`(city, district)` pair, stored in a separate normalised table:

```
job_id | sort_order | city        | district
-------|------------|-------------|----------
abc123 | 0          | Hà Nội      | Cầu Giấy
abc123 | 1          | Hà Nội      | Đống Đa
def456 | 0          | Hồ Chí Minh | Quận 7
```

#### 1.3 Job title normalization → `job_role_category`

`etl/transform/job_title.py` uses a **3-stage pipeline** to classify every title into one of 14 categories:

1. **Noise stripping** — removes parentheticals, salary hints, job codes  
2. **Rule-based matching** — keyword lookup (ordered by specificity, bilingual EN/VI)  
3. **TF-IDF fallback** — char n-gram cosine similarity against seed phrases (handles typos & Vietnamese variants)

| Category | Example titles |
|---|---|
| Software Development | Senior Backend Developer, Lập Trình Viên PHP |
| QA & Testing | Automation Tester, Chuyên Viên Kiểm Thử |
| DevOps & Cloud | DevOps/SRE, Chuyên Viên Vận Hành Cloud |
| Data & Analytics | Data Engineer, AI Engineer, Chuyên Gia Big Data |
| Business Analysis | Business Analyst, BRSE, Kỹ Sư Cầu Nối |
| Project & Product Management | Product Owner, Scrum Master |
| Network & Infrastructure | Network Engineer, DBA |
| IT & Technical Support | Helpdesk, Nhân Viên IT |
| Security | Cybersecurity Analyst, Pentest Engineer |
| Design & UX | UI/UX Designer, Graphic Designer |
| Marketing & Content | SEO Specialist, Content Writer |
| Sales & Business Development | Business Development, Telesales |
| Technical Writing | Technical Writer |
| Other | Anything that does not match |

Results on real data: **99.3% classified** (only 14/1 933 rows fall to "Other").

---

### Requirement 2 — Data Pipeline

#### 2.1 ETL flow

```
data/raw/data.csv
      │
      ▼
[ Extract ]  etl/extract/extract.py
  • Read CSV (UTF-8 with Latin-1 fallback)
  • Validate required columns ("salary")
  • Raise ExtractError on empty file or missing columns
      │
      ▼
[ Transform ]  etl/transform/transform.py
  • Generate stable job_id  (MD5 of link + company + title + date)
  • Parse salary   → min_salary, max_salary, salary_unit
  • Classify title → job_role_category
  • Expand address → (city, district) pairs
  • Save snapshots → data/processed/salary_cleaned.csv
                      data/processed/job_locations.csv
      │
      ▼
[ Load ]  etl/load/load.py
  • Pre-flight connection check
  • Single transaction (engine.begin()):
      TRUNCATE job_locations  ← child first (respects FK)
      TRUNCATE records
      INSERT   records        ← parent first (satisfies FK on insert)
      INSERT   job_locations
  • Either all tables commit or all roll back
```

#### 2.2 Error handling

Custom exception hierarchy in `etl/errors.py`:

```
ETLError
├── ExtractError   — file not found, unreadable, empty, missing columns
├── TransformError — empty DataFrame, missing salary column, CSV write failure
├── LoadError      — DB unreachable, write failure (triggers full rollback)
└── ConfigError    — missing environment variables
```

`main.py` catches each exception type separately, logs a clear message, and returns a non-zero exit code so cron and CI/CD detect failures automatically.

#### 2.3 Scheduled execution

| Method | File | Schedule |
|---|---|---|
| **Cron (local)** | `scripts/run_pipeline.sh` + `scripts/crontab.example` | Configure freely |
| **GitHub Actions** | `.github/workflows/etl-scheduled.yml` | Daily 06:00 UTC + manual trigger |

---

### Requirement 3 — Data Analysis

All charts are produced in `notebooks/salary_analysis.ipynb` and saved to `reports/figures/`.  
Reproduce them by running every cell in the notebook.

---

#### 3.1 Salary Distribution by Job Position

**Approach**

1. Load `data/processed/salary_cleaned.csv`.
2. Drop rows where both `min_salary` and `max_salary` are null (genuinely negotiable / missing).
3. Convert USD → VND at a fixed rate (1 USD = 25,000 VND) so all values are comparable.
4. Scale to **millions of VND** for readability.
5. Compute `mid_salary = (min + max) / 2`; remove extreme outliers (`mid_salary > 200 triệu`).
6. Plot four complementary views.

**Chart 1 — Box plot: spread & outliers per category**

![Salary box plot](reports/figures/salary_boxplot.png)

> Each box shows the interquartile range (25th–75th percentile) of mid-salary.
> DevOps & Cloud and Data & Analytics sit at the top; IT & Technical Support at the bottom.

---

**Chart 2 — Median salary bar: ranked pay per category**

![Median salary bar](reports/figures/salary_median_bar.png)

> Sorted horizontal bar with the exact median value labelled.
> Useful for a quick salary benchmark per role.

---

**Chart 3 — KDE histogram: salary density for the top 3 categories**

![KDE histogram](reports/figures/salary_kde_top3.png)

> Kernel Density Estimation (KDE) overlaid on a histogram.
> Shows the full shape of the distribution, not just the median.
> Software Development has the widest spread; QA & Testing is more concentrated around 10–15 triệu.

---

**Chart 4 — Dual-axis: job count vs median salary**

![Count vs median](reports/figures/salary_count_vs_median.png)

> Left axis = number of job postings (bars); right axis = median mid-salary (line).
> Key insight: **volume ≠ pay** — Software Development dominates in headcount but not always in median salary.

---

#### 3.2 Heatmap — Job Distribution by Region

**Approach**

1. Merge `job_locations.csv` (city per job) with `salary_cleaned.csv` (category per job) on `job_id`.
2. Filter to the **top 10 cities** by posting count; exclude generic entries (`Toàn Quốc`, `Nước Ngoài`).
3. Filter to the **top 10 categories** by posting count.
4. Build a pivot table: rows = cities, columns = categories, values = job count.
5. Produce two views — raw count and row-normalised percentage.

**Chart 5 — Count heatmap (city × category)**

![Region heatmap count](reports/figures/heatmap_region_category_count.png)

> Raw number of job postings per city–category pair.
> Hà Nội and Hồ Chí Minh dominate every category due to sheer volume.

---

**Chart 6 — % mix heatmap (normalised per city)**

![Region heatmap pct](reports/figures/heatmap_region_category_pct.png)

> Each row sums to 100%, removing the volume bias.
> Key findings:
> - **Nghệ An** is almost entirely Software Development (87.5%) — very specialised market.
> - **Bình Dương** has unusually high IT & Technical Support (52.6%) — manufacturing-adjacent IT.
> - **Đà Nẵng** skews more toward Software Development (69.3%) than HCM or Hà Nội.
> - **Đồng Nai / Hải Phòng** lean on IT & Technical Support / Network & Infrastructure, matching their industrial-zone character.

---

#### 3.3 Trend Chart — In-Demand (Hot) Technologies

**Approach**

The dataset is a single-day scrape (2023-08-01). Each job's `time` field encodes
**"Còn N ngày để ứng tuyển"** (N days remaining to apply), which lets us
reverse-engineer an approximate posting date:

```
days_ago ≈ 30 − days_left     (for standard 30-day posting windows)
```

Steps:

1. Filter to jobs with `days_left` between 1–30 (standard 30-day posting window).
2. Define 18 technology keyword patterns (regex) matched against lowercased `job_title`.
3. Bucket postings into **4 weekly cohorts** (oldest Week 4 → latest Week 1).
4. Compute each technology's **% share of that week's postings**.
5. Plot two panels — weekly % trend lines (top 10 techs) and overall snapshot bar (all techs).

**Chart 7 — Technology trend (weekly lines + snapshot bar)**

![Tech trend](reports/figures/tech_trend.png)

> Key findings:
> - **Java (123 postings)** is the dominant language, consistently 6–8% of weekly postings.
> - **PHP (70) and React (69)** are neck-and-neck as the second tier; React shows an uptick in the latest week.
> - **Mobile** (Android 39 + Flutter/Dart 25 + Swift/iOS 24 = 88 combined) rivals Python (37) — mobile is a major hiring segment.
> - **AI/ML (20), Go (20), Data Engineering (16)** are present but still niche relative to the mainstream stack.
> - Week-to-week fluctuations reflect sample noise; the snapshot bar (Panel B) is the more reliable signal.

> ⚠️ **Note:** The time axis is reverse-engineered from "days remaining to apply" — an approximation,
> not a real timestamp. See Chart 8 below for a fully real-data alternative.

---

#### 3.4 Technology Demand by City (Real Geographic Trend)

**Approach**

Rather than approximating time, this chart uses **actual location data** from `job_locations.csv`
— a genuine dimension that requires no inference.

1. Merge `job_locations` with `salary_cleaned` on `job_id`; deduplicate to one row per job.
2. Detect technologies by matching 14 regex patterns against lowercased `job_title`.
3. For each city compute: `% of that city's jobs mentioning the technology`.
4. Filter to cities with **≥ 15 jobs** (smaller samples produce unreliable percentages).
5. Plot as lines (Panel A — geographic shift) and heatmap (Panel B — full matrix).

**Chart 8 — Tech demand by city (line chart + heatmap)**

![Tech by location](reports/figures/tech_by_location.png)

> Key findings:
> - **Java peaks sharply in Đà Nẵng (11.4%)** — highest of any tech in any city; strong outsourcing concentration.
> - **PHP dominates Hồ Chí Minh (6.1%)** over all other cities — driven by HCM's large web/e-commerce sector.
> - **Android + React are both 6.8% in Đà Nẵng** — mobile and frontend are proportionally more active there than in Hà Nội or HCM.
> - **PHP is 0% in Đà Nẵng** — sharp contrast with HCM; Đà Nẵng companies prefer Java and mobile stacks.
> - **Hà Nội is the most balanced** — no single technology dominates; demand is spread across Java, PHP, React, Android, Python.

---

## Project Layout

```
basic-etl-pipeline/
├── config/
│   ├── schema.sql          # PostgreSQL DDL (PK, FK, indexes) — applied on first Docker run
│   └── settings.py         # Loads .env, get_engine(), directory constants
├── data/
│   ├── raw/                # Source CSV files
│   └── processed/          # salary_cleaned.csv, job_locations.csv (written after each run)
├── etl/
│   ├── __init__.py
│   ├── errors.py           # Custom exception hierarchy
│   ├── extract/extract.py  # CSV → DataFrame
│   ├── transform/
│   │   ├── salary.py       # Salary string → (min, max, unit)
│   │   ├── address.py      # Address string → [(city, district), …]
│   │   ├── job_title.py    # Title → category (rules + TF-IDF)
│   │   └── transform.py    # Orchestrates all transform steps
│   └── load/load.py        # TRUNCATE + INSERT in one transaction
├── notebooks/
│   └── salary_analysis.ipynb  # All analysis charts
├── reports/figures/           # PNG outputs from the notebook
├── scripts/
│   ├── run_pipeline.sh        # Shell wrapper for cron
│   └── crontab.example        # Example cron entry
├── tests/
│   ├── test_salary.py      # 25 cases
│   ├── test_address.py     # 13 cases
│   └── test_job_title.py   # 32 cases
├── .github/workflows/
│   └── etl-scheduled.yml   # GitHub Actions daily schedule
├── .env.example            # Template — copy to .env and fill in
├── docker-compose.yml      # PostgreSQL 16 + pgAdmin
├── main.py                 # CLI entrypoint
└── requirements.txt        # Pinned dependencies
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [Docker](https://docs.docker.com/get-docker/) with Docker Compose

### 2. Install

```bash
git clone <repo-url>
cd basic-etl-pipeline

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — set DB_HOST=localhost and keep other defaults or adjust to your setup
```

### 4. Start the database

```bash
docker compose up -d
# Schema (tables, FK, indexes) is applied automatically on first volume creation
```

### 5. Run the pipeline

```bash
python main.py data/raw/data.csv
```

Expected output:

```
2024-01-01 06:00:00 INFO etl.extract.extract: Extracted 1933 rows from data/raw/data.csv
2024-01-01 06:00:01 INFO etl.transform.transform: rows: 1933 | salary parsed: 1223 | unparseable (had digit): 0
2024-01-01 06:00:03 INFO etl.load.load: Loaded 1933 rows into records
2024-01-01 06:00:03 INFO etl.load.load: Loaded 2166 rows into job_locations
2024-01-01 06:00:03 INFO __main__: rows extracted: 1933 / loaded: 1933 records, 2166 job_locations
```

Optional CLI flags:

```bash
python main.py data/raw/data.csv --table records --locations-table job_locations
LOG_LEVEL=DEBUG python main.py data/raw/data.csv   # verbose output
```

### 6. Run unit tests

```bash
python -m pytest tests/ -v
# 70 passed in ~1s
```

### 7. Open the analysis notebook

```bash
jupyter notebook notebooks/salary_analysis.ipynb
```

---

## Inspecting the database

**pgAdmin:** [http://localhost:8080](http://localhost:8080) — sign in with `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` from `.env`.

**psql:**

```bash
docker compose exec postgres psql -U "$DB_USER" -d "$DB_NAME"
```

Useful queries:

```sql
-- Jobs with all their locations
SELECT r.job_title, r.job_role_category, l.city, l.district
FROM records r
LEFT JOIN job_locations l ON r.job_id = l.job_id
LIMIT 20;

-- Salary stats per category (VND only)
SELECT job_role_category,
       COUNT(*)                              AS jobs,
       ROUND(AVG(min_salary) / 1e6, 1)      AS avg_min_m,
       ROUND(AVG(max_salary) / 1e6, 1)      AS avg_max_m
FROM records
WHERE salary_unit = 'VND'
GROUP BY job_role_category
ORDER BY avg_max_m DESC NULLS LAST;

-- Top hiring cities
SELECT city, COUNT(*) AS postings
FROM job_locations
GROUP BY city
ORDER BY postings DESC
LIMIT 10;
```

---

## Scheduled runs

**Local (cron):**

```bash
# Add to crontab -e (mkdir -p logs must run before >> opens logs/pipeline.log)
15 6 * * * cd /path/to/basic-etl-pipeline && mkdir -p logs && ./scripts/run_pipeline.sh >> logs/pipeline.log 2>&1
```

**GitHub Actions:** set repository secrets `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`  
pointing to a publicly reachable PostgreSQL instance (localhost will not work from GitHub runners).  
Workflow runs daily at 06:00 UTC and can be triggered manually via **workflow_dispatch**.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named 'config'` | Run `python main.py` from the project root, not from inside a subdirectory |
| `Connection refused` | `docker compose ps` — Postgres must be running; `DB_HOST=localhost` when running on host |
| `Password authentication failed` | Check `.env` matches the credentials Docker used on the first volume creation; if they changed, run `docker compose down -v` and restart |
| `ConfigError: Missing required environment variable` | Copy `.env.example` to `.env` and fill in all five DB variables |
| Salary parse rate seems low | Expected — ~37% of salaries are genuinely "Thoả thuận" / negotiable / blank |
