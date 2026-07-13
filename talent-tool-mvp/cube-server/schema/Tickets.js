// Cube.js schema — Tickets cube
// Powers the customer-success dashboard and the agent-performance
// dashboard (tickets are a primary customer signal).

cube(`Tickets`, {
  sql: `SELECT * FROM tickets`,

  joins: {
    Roles: {
      sql: `${CUBE}.role_id = ${Roles}.id`,
      relationship: `belongsTo`,
    },
  },

  dimensions: {
    id: {
      sql: `id`,
      type: `string`,
      primaryKey: true,
    },
    title: {
      sql: `title`,
      type: `string`,
    },
    orgId: {
      sql: `org_id`,
      type: `string`,
    },
    assigneeId: {
      sql: `assignee_id`,
      type: `string`,
    },
    priority: {
      sql: `priority`,
      type: `string`,
    },
    status: {
      sql: `status`,
      type: `string`,
    },
    category: {
      sql: `category`,
      type: `string`,
    },
    sentiment: {
      sql: `sentiment`,
      type: `string`,
    },
    slaBreached: {
      sql: `sla_breached`,
      type: `boolean`,
    },
    createdAt: {
      sql: `created_at`,
      type: `time`,
    },
    closedAt: {
      sql: `closed_at`,
      type: `time`,
    },
  },

  measures: {
    count: {
      type: `count`,
      title: `工单总数`,
    },
    openCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.status IN ('open', 'in_progress')` }],
      title: `未结工单`,
    },
    closedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.status = 'closed'` }],
      title: `已结工单`,
    },
    slaBreachCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.sla_breached = true` }],
      title: `SLA 违约数`,
    },
    negativeCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.sentiment = 'negative'` }],
      title: `负面情绪工单`,
    },
    positiveCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.sentiment = 'positive'` }],
      title: `正面情绪工单`,
    },
    avgResolutionHours: {
      sql: `EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600`,
      type: `avg`,
      title: `平均解决时长 (h)`,
    },
    slaBreachRate: {
      sql: `CASE WHEN ${CUBE}.sla_breached THEN 1 ELSE 0 END`,
      type: `avg`,
      title: `SLA 违约率`,
    },
    npsProxy: {
      // (positive - negative) / total — 客户成功 NPS 代理
      sql: `CASE
              WHEN ${CUBE}.sentiment = 'positive'  THEN 100
              WHEN ${CUBE}.sentiment = 'negative'  THEN -100
              ELSE 0
            END`,
      type: `avg`,
      title: `NPS 代理分`,
    },
  },

  preAggregations: {
    main: {
      type: `rollup`,
      measures: [count, openCount, slaBreachCount, slaBreachRate, npsProxy],
      dimensions: [status, priority, category, sentiment, assigneeId],
      refreshKey: { every: `5 minutes` },
    },
  },
});
