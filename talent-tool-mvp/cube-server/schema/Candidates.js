// Cube.js schema — Candidates cube
// Maps the `candidates` table to a dimensional model used across the BI
// dashboards (HR funnel, recruitment efficiency, channel ROI, agent
// performance, customer success).

cube(`Candidates`, {
  sql: `SELECT * FROM candidates`,

  // -------------------------------------------------------------
  // Joins — used by the candidate × matches view
  // -------------------------------------------------------------
  joins: {
    Matches: {
      sql: `${CUBE}.id = ${Matches}.candidate_id`,
      relationship: `hasMany`,
    },
  },

  // -------------------------------------------------------------
  // Dimensions
  // -------------------------------------------------------------
  dimensions: {
    id: {
      sql: `id`,
      type: `string`,
      primaryKey: true,
    },
    name: {
      sql: `full_name`,
      type: `string`,
    },
    email: {
      sql: `email`,
      type: `string`,
    },
    orgId: {
      sql: `org_id`,
      type: `string`,
    },
    source: {
      sql: `source`,
      type: `string`,
    },
    channel: {
      sql: `COALESCE(channel, source)`,
      type: `string`,
    },
    stage: {
      sql: `current_stage`,
      type: `string`,
    },
    status: {
      sql: `status`,
      type: `string`,
    },
    city: {
      sql: `city`,
      type: `string`,
    },
    seniority: {
      sql: `seniority`,
      type: `string`,
    },
    gender: {
      sql: `gender`,
      type: `string`,
    },
    createdAt: {
      sql: `created_at`,
      type: `time`,
    },
    updatedAt: {
      sql: `updated_at`,
      type: `time`,
    },
  },

  // -------------------------------------------------------------
  // Measures
  // -------------------------------------------------------------
  measures: {
    count: {
      type: `count`,
      title: `候选人总数`,
    },
    distinctOrgs: {
      sql: `org_id`,
      type: `countDistinct`,
      title: `触达组织数`,
    },
    avgMatchScore: {
      sql: `${Matches}.score`,
      type: `avg`,
      title: `平均匹配分`,
    },
    highIntentCount: {
      sql: `id`,
      type: `count`,
      filters: [{ sql: `${CUBE}.intent_score >= 0.7` }],
      title: `高意向候选人`,
    },
  },

  // -------------------------------------------------------------
  // Pre-aggregations
  // -------------------------------------------------------------
  preAggregations: {
    main: {
      type: `rollup`,
      measures: [count, highIntentCount],
      dimensions: [source, channel, stage, city, seniority],
      refreshKey: { every: `5 minutes` },
    },
  },
});
