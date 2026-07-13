# Waibao BI — Cube.js service (T2802)

A standalone Cube.js server that powers the BI / analytics layer of the
Waibao platform. It exposes a REST API on `/cubejs-api/v1` that:

- Speaks the standard [Cube.js REST protocol](https://cube.dev/docs/rest-api)
- Connects to either the OLTP Postgres (`PG_*`) or the analytics
  warehouse (`WAREHOUSE_*`) populated by `backend/services/warehouse/etl_pipeline.py`
- Exposes 4 cubes — `Candidates`, `Roles`, `Matches`, `Tickets` — that
  cover the 5 built-in BI dashboards (HR funnel, recruitment efficiency,
  channel ROI, agent performance, customer success)

## Run

```bash
cd cube-server
npm install
cp .env.example .env  # edit secrets
npm start
```

The server listens on port 4000 by default. The frontend BI page and
`backend/api/bi.py` proxy hit it through `CUBEJS_URL`.

## Schema

See `schema/Candidates.js`, `schema/Roles.js`, `schema/Matches.js`,
`schema/Tickets.js`. Each cube has dimensions, measures, and a 5-minute
roll-up pre-aggregation.

## Endpoints

| Method | Path                | Description                  |
| ------ | ------------------- | ---------------------------- |
| GET    | `/cubejs-api/v1/meta`  | Cube + dimension + measure metadata |
| POST   | `/cubejs-api/v1/load`  | Run a query and return rows  |
| GET    | `/cubejs-api/v1/sql`   | Show generated SQL (debug)   |
