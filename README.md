# AI Dashboard Generator

Upload your own CSV or Excel files, ask a question in plain language, and get a dashboard built around that question. The system profiles your data, builds a schema, loads it into SQL Server, and uses an LLM to plan the dashboard and write the SQL behind each chart.

> Final-year engineering project (PFE), Business Intelligence specialization.
> Status: working MVP. Orchestration with LangGraph is planned, not implemented yet.

## How it works

1. **Upload** one or more CSV/Excel files in the Streamlit interface.
2. **Standardize**: table and column names are converted to `snake_case`, date columns are parsed.
3. **Profile**: column types, statistics and relationships between tables are detected.
4. **Build the schema** given to the LLM, including a `DATA COVERAGE` section with the min and max of every date column.
5. **Load into a workspace database** (`dashboard_workspace` on SQL Server). It is created if missing and rebuilt on every upload.
6. **Ask a question.** The planner proposes 4 to 6 KPIs and charts grounded in the schema.
7. **SQL agent** generates, extracts, validates and executes the SQL for each item, then Plotly renders the result.

### SQL agent stages

| Stage | What happens | On failure |
|---|---|---|
| `generation` | The LLM writes a candidate query from the question and the schema | Stop |
| `extraction` | The SQL is isolated from the response, cleaned and fixed for T-SQL (for example `LIMIT` becomes `TOP`) | Stop |
| `validation` / `schema_validation` | Tables and qualified columns are checked against the real database | Retry with feedback |
| `execution` | Only a single `SELECT`/`WITH` statement is allowed to run | Retry with feedback |
| `completed` | The result is returned | |

**Self-correction:** schema rejections, execution errors and empty results are sent back to the model together with the error message, up to 3 attempts. Refusals (`SELECT 'INVALID QUERY'`), non-SQL answers and API errors stop immediately. Every attempt is recorded in `history`.

## Quick start

### Prerequisites

- Python 3.11 or newer
- Docker Desktop
- Microsoft ODBC Driver for SQL Server (version 17 or 18) installed on the machine that runs Streamlit
- A [Groq](https://console.groq.com) API key

### 1. Clone and install

```bash
git clone https://github.com/meriem0410/AI-dashboard-generator.git
cd AI-dashboard-generator
python -m venv .venv
.venv\Scripts\activate          # Windows; use "source .venv/bin/activate" on Linux/macOS
pip install -r requirements.txt
```

### 2. Configure

```bash
copy .env.example .env          # Linux/macOS: cp .env.example .env
```

Edit `.env`: set `GROQ_API_KEY`, and choose a strong `DB_PASSWORD` (at least 8 characters with upper case, lower case, digits and symbols, otherwise SQL Server refuses to start). Never commit `.env`.

### 3. Start the database

```bash
docker compose up -d db
docker compose ps               # wait until the status is "healthy"
```

SQL Server is published on host port **14330** (not 1433), so it never clashes with a SQL Server installed on your machine.

### 4. Run the app

```bash
python -m streamlit run app.py
```

Open http://localhost:8501, upload your files, click **Load dataset**, then ask your question.

### Fully containerized run (experimental)

```bash
docker compose up --build
```

This also builds the Streamlit image. It has not been validated end to end yet.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | none (required) | Groq API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Model used for SQL generation and dashboard planning |
| `DB_HOST` | `localhost` | Database host (`db` inside Docker Compose) |
| `DB_PORT` | `14330` | Database port on the host |
| `DB_NAME` | `dashboard_workspace` | Workspace database. The name must contain `workspace`, because all of its tables are dropped on every upload |
| `DB_USER` | `sa` | SQL Server login |
| `DB_PASSWORD` | none (required) | Password of the SQL Server login |
| `ODBC_DRIVER` | auto-detected | Optional. Overrides the detected ODBC driver name |

## Project structure

```
app.py                      Streamlit interface: upload, overview, question, dashboard
config.py                   Environment-driven configuration (LLM client, database engine)
loader.py                   CSV/Excel loading
docker-compose.yml          SQL Server (and the app, experimental)
Dockerfile                  Streamlit image with the ODBC driver
Modules/
  pipeline.py               UI-independent steps: ingest, profile, schema, load, answer, visual
  prompt_builder.py         SQL generation prompt
  sql_generator.py          LLM call, SQL extraction and cleaning
  sql_validator.py          Schema validation and T-SQL fixes
  sql_executor.py           Read-only execution
  profiler.py               Data profiling
  schema_builder.py         Schema text for the LLM
  visualisation.py          Chart selection and rendering
  Agents/
    Agent_data.py           Data ingestion
    Agent_sql.py            Staged SQL agent with self-correction
```

## Troubleshooting

- **`IM002 Data source name not found`**: no suitable ODBC driver is installed. Run `python -c "import pyodbc; print(pyodbc.drivers())"` and install "ODBC Driver 17 or 18 for SQL Server" if none is listed.
- **`Login failed for user 'sa'` while `docker compose ps` says healthy**: another SQL Server is probably answering on the port you use. Check that `DB_PORT=14330` in `.env`, and look at `netstat -ano | findstr :1433`.
- **`Login failed` right after the first start**: the container was created with a blank or weak password and the volume kept that setup. Fix `DB_PASSWORD` in `.env`, then run `docker compose down -v` and `docker compose up -d db`.
- **`Cannot open database "dashboard_workspace"` (error 4060)**: the workspace database does not exist yet. It is created automatically when you click **Load dataset**, so make sure you are running the current `Modules/pipeline.py`.

## Known limitations

- The validator checks tables and qualified columns (`table.column`) only. Unqualified columns, syntax and business semantics are not validated before execution; execution errors are handled by the retry loop.
- The SQL prompt contains examples and date-column names from the logistics test dataset, which limits generality.
- Only columns whose name contains `date` are parsed as dates.
- One shared workspace database: one user at a time.
- Each retry costs an extra model call (up to 3 per chart).

## Roadmap

- LangGraph orchestration of the staged functions
- Evaluation set with expected behavior per question
- Per-session workspace databases
- Schema-driven few-shot examples
- Cloud deployment with a managed database

## Test dataset

The development tests use a logistics dataset from Kaggle (12 CSV files: customers, drivers, trucks, trailers, loads, trips, routes, facilities, fuel purchases, delivery events, maintenance records, safety incidents). The data is not included in this repository. Add the link to the Kaggle dataset here: `[dataset link]`.