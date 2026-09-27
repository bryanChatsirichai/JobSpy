# Pagination & result limits

How the FastAPI sidecar and scrape scripts control “pages”, job sites, and how many jobs are fetched.

---

## Running the API backend

### Prerequisites

From the repo root (`JobSpy/`):

1. Install dependencies (e.g. `uv sync` or your usual Poetry/venv setup).
2. Copy env config: `cp .env.example .env` (Windows: copy `.env.example` → `.env`).
3. Edit `.env` for sites, location, search terms, and limits. The API loads `JobSpy/.env` automatically via `jobspy_api/config.py`.

### Start the server

```bash
uv run uvicorn jobspy_api.main:app --host 0.0.0.0 --port 8001
```

Use the same port as `JOBSPY_PORT` in `.env` (default **8001**) so clients and docs stay aligned.

The process runs until you stop it (Ctrl+C). Scrapes run inside request handlers and can take a while per call.

### Interactive docs

With the server running:

| URL | Purpose |
|-----|---------|
| http://localhost:8001/docs | Swagger UI (try endpoints) |
| http://localhost:8001/redoc | ReDoc |

### Endpoints

Routes are registered **twice** (with and without `/v1`). Use either prefix; behavior is the same.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` or `/v1/health` | Liveness check. Returns `{"status":"ok"}`. |
| `GET` | `/jobs/search` or `/v1/jobs/search` | Scrape **one** search term (see `page`) across all configured sites. |

#### `GET /jobs/search` query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int ≥ 0 | `0` | 0-based index into `JOBSPY_SEARCH_TERMS` |
| `results_wanted` | int 1–1000 | `JOBSPY_RESULTS_WANTED` from `.env` | Max jobs **per site** for this term |
| `hours_old` | int ≥ 1 | `JOBSPY_HOURS_OLD` from `.env` | Only jobs posted within this many hours |

#### Example requests

```http
GET http://localhost:8001/v1/health
```

```http
GET http://localhost:8001/v1/jobs/search?page=0
GET http://localhost:8001/v1/jobs/search?page=0&results_wanted=50&hours_old=504
```

#### Example success response (`/jobs/search`)

```json
{
  "success": true,
  "page": 0,
  "search_term": "(all jobs)",
  "total_terms": 29,
  "has_more": true,
  "jobs": [
    {
      "site": "indeed",
      "title": "...",
      "company": "...",
      "job_url": "...",
      "search_term": "(all jobs)"
    }
  ]
}
```

On scrape failure, `success` is `false` and `jobs` is `[]`. When `page` is past the last term, `success` is `true`, `search_term` is `null`, `has_more` is `false`, and `jobs` is `[]`.

CORS is enabled for `GET` from any origin (portal-friendly).

---

## Quick reference

| Concept | What it controls | Separate or mixed? |
|---------|------------------|-------------------|
| API `page` | Which **search term** to run (0-based index) | One term per request |
| `JOBSPY_SITE_NAMES` / `site_name` | Which **job boards** to hit | All sites run **together** per term |
| `results_wanted` | Max jobs **per site**, per term | Results merged into one list |
| Job-board “page 2, 3…” | Internal scraping inside JobSpy | Handled automatically; not exposed by API |

---

## API `page` = search term, not job site

In `GET /jobs/search`, **`page` is not a job-board page** and **not a site selector**. It is a **0-based index into `SEARCH_TERMS`**.

| `page` | Scrapes |
|--------|---------|
| `0` | First term (default: `null` → location-only / all jobs) |
| `1` | Second term (e.g. `"full time"`) |
| … | … |
| `N-1` | Last configured term |

Configure terms via `JOBSPY_SEARCH_TERMS` in `.env` (JSON array). See `.env.example`.

### Sites are mixed, not paginated separately

Each request runs **one search term** across **every** site in `JOBSPY_SITE_NAMES` at once:

```
GET /jobs/search?page=0
  search term: "(all jobs)"
    ├── indeed     → up to results_wanted jobs
    ├── linkedin   → up to results_wanted jobs
    ├── glassdoor  → up to results_wanted jobs
    ├── google     → up to results_wanted jobs
    └── bayt       → up to results_wanted jobs
  → single jobs[] array (mixed, not grouped by site)
```

JobSpy scrapes sites **concurrently** (`ThreadPoolExecutor`), then combines rows into one response. Each job has a `site` field (`indeed`, `linkedin`, etc.) so you can filter client-side.

**Not supported today:**

| You might expect… | Actual behavior |
|-------------------|-----------------|
| `page=0` → Indeed, `page=1` → LinkedIn | Every `page` hits **all** configured sites |
| Paginate Indeed page 2, then page 3 via API | Board pagination is internal to JobSpy only |
| `?site=indeed` query param | No site filter on `/jobs/search`; use `JOBSPY_SITE_NAMES` in `.env` |

Same behavior in `scrape_sg_original.py` and `scrape_sg.py`: each loop iteration passes all sites to one `scrape_jobs()` call, then concatenates results.

### Response fields

- `page` — term index used
- `search_term` — human-readable label for that term
- `total_terms` — length of `SEARCH_TERMS`
- `has_more` — `true` when `page + 1 < total_terms`
- `jobs` — mixed list from all sites; deduped by `job_url` within the term

### Example: sweep all terms

```http
GET /jobs/search?page=0&results_wanted=50
GET /jobs/search?page=1&results_wanted=50
…
```

Advance `page` until `has_more` is `false`.

---

## Job-board pagination (internal to JobSpy)

Neither the API nor the scrape scripts expose “results per page” on Indeed, LinkedIn, etc. The library paginates **each site independently** until it collects `results_wanted` jobs (or hits site limits), then merges.

Approximate internal request sizes:

| Site | Jobs per internal request |
|------|---------------------------|
| Indeed | 100 |
| LinkedIn | 25 |
| Glassdoor | 30 |
| Google | 10 |
| Bayt | varies |

Boards typically cap around ~1000 results per search. LinkedIn is the most restrictive (often rate-limits after ~10 internal pages without proxies).

---

## `results_wanted` — jobs per site, per term

`results_wanted` is how many listings JobSpy tries to fetch **from each site** for **one search term**.

Example: 5 sites × `results_wanted=5` → up to ~25 raw rows per API call, before dedup by `job_url`.

### Where it is set

| Source | Used by |
|--------|---------|
| Hardcoded `RESULTS_WANTED = 5` in `scrape_sg_original.py` | Original standalone script only |
| `JOBSPY_RESULTS_WANTED` in `.env` (default `5`) | API + `scrape_sg.py` |
| Query param `?results_wanted=N` on `/jobs/search` (1–1000) | API only; overrides env when provided |

Related: `hours_old` / `JOBSPY_HOURS_OLD` filters by job age (default 504 h = 3 weeks).

---

## Script vs API

| | `scrape_sg_original.py` | `scrape_sg.py` | API `/jobs/search` |
|--|-------------------------|----------------|---------------------|
| Terms per run | All terms in a loop | All terms (CLI) | One term per request (`page`) |
| Sites per term | All `SITE_NAMES` together | All `SITE_NAMES` together | All `JOBSPY_SITE_NAMES` together |
| Output shape | One CSV, mixed sites | One CSV, mixed sites | One JSON `jobs` array, mixed sites |
| `results_wanted` | Constant in file | `--results-wanted` or `.env` | Query param or `.env` |
| Job-board pages | JobSpy internal | JobSpy internal | JobSpy internal |

---

## Tuning examples

**More jobs per site for one term (API):**

```http
GET /jobs/search?page=0&results_wanted=200
```

**Scrape fewer boards (env — affects API and `scrape_sg.py`):**

```env
JOBSPY_SITE_NAMES=indeed,glassdoor,google
```

**Change default result count:**

```env
JOBSPY_RESULTS_WANTED=100
```

**Change only the original script:** edit `RESULTS_WANTED` in `scrape_sg_original.py`.
