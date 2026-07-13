// Cube.js configuration for Waibao BI
// Phase: T2802 — BI (Cube.js) layer
//
// Reads env from .env (PG_WAREHOUSE_URL points to the analytics warehouse
// populated by backend/services/warehouse/etl_pipeline.py).
//
// This service exposes a REST API on /cubejs-api/v1 used by the frontend
// BI page and proxied by backend/api/bi.py with a 5-minute Redis cache.

require("dotenv").config();

module.exports = {
  // -------------------------------------------------------------
  // API
  // -------------------------------------------------------------
  apiSecret:
    process.env.CUBEJS_API_SECRET ||
    "waibao-bi-dev-secret-CHANGE-ME-IN-PROD",

  // -------------------------------------------------------------
  // DB driver (Postgres — typically the warehouse schema, not OLTP)
  // -------------------------------------------------------------
  driverFactory: ({ dataSource } = {}) => {
    if (dataSource === "warehouse") {
      return new (require("@cubejs-backend/postgres-driver"))({
        database: process.env.WAREHOUSE_DB || "waibao_warehouse",
        host: process.env.WAREHOUSE_HOST || "localhost",
        user: process.env.WAREHOUSE_USER || "warehouse",
        password: process.env.WAREHOUSE_PASSWORD || "warehouse",
        port: parseInt(process.env.WAREHOUSE_PORT || "5432", 10),
        ssl: process.env.WAREHOUSE_SSL === "true",
      });
    }
    return new (require("@cubejs-backend/postgres-driver"))({
      database: process.env.PG_DATABASE || "waibao",
      host: process.env.PG_HOST || "localhost",
      user: process.env.PG_USER || "postgres",
      password: process.env.PG_PASSWORD || "postgres",
      port: parseInt(process.env.PG_PORT || "5432", 10),
      ssl: process.env.PG_SSL === "true",
    });
  },

  // -------------------------------------------------------------
  // Schema location
  // -------------------------------------------------------------
  schemaPath: "schema",

  // -------------------------------------------------------------
  // Cache / scheduled refresh — 5 minutes for everything
  // -------------------------------------------------------------
  scheduledRefreshTimer: 300, // seconds
  queryCache: {
    refreshKeyRenewalThreshold: 30,
    backgroundRenew: true,
    queueOptions: {
      concurrency: 4,
    },
  },

  // -------------------------------------------------------------
  // Production tuning
  // -------------------------------------------------------------
  http: {
    cors: {
      origin: process.env.CUBEJS_CORS_ORIGIN || "*",
      credentials: true,
    },
  },

  // -------------------------------------------------------------
  // Telemetry
  // -------------------------------------------------------------
  telemetry: false,
  devServer: false,
};
