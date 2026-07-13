// Cube.js schema — Matches cube
// The bread-and-butter of recruitment analytics: candidate × role pairings
// with match score, status, and agent attribution.

cube(`Matches`, {
  sql: `SELECT * FROM matches`,

  joins: {
    Candidates: {
      sql: `${CUBE}.candidate_id = ${Candidates}.id`,
      relationship: `belongsTo`,
    },
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
    candidateId: {
      sql: `candidate_id`,
      type: `string`,
    },
    roleId: {
      sql: `role_id`,
      type: `string`,
    },
    orgId: {
      sql: `org_id`,
      type: `string`,
    },
    status: {
      sql: `status`,
      type: `string`,
    },
    decision: {
      sql: `decision`,
      type: `string`,
    },
    agentId: {
      sql: `agent_id`,
      type: `string`,
    },
    agentName: {
      sql: `agent_name`,
      type: `string`,
    },
    channel: {
      sql: `channel`,
      type: `string`,
    },
    scoreBucket: {
      // bucketed score → easier to chart
      sql: `CASE
              WHEN score >= 0.9 THEN '90-100'
              WHEN score >= 0.8 THEN '80-90'
              WHEN score >= 0.7 THEN '70-80'
              WHEN score >= 0.6 THEN '60-70'
              ELSE '<60'
            END`,
      type: `string`,
    },
    createdAt: {
      sql: `created_at`,
      type: `time`,
    },
    decidedAt: {
      sql: `decided_at`,
      type: `time`,
    },
  },

  measures: {
    count: {
      type: `count`,
      title: `匹配总数`,
    },
    avgScore: {
      sql: `score`,
      type: `avg`,
      title: `平均匹配分`,
    },
    maxScore: {
      sql: `score`,
      type: `max`,
      title: `最高匹配分`,
    },
    minScore: {
      sql: `score`,
      type: `min`,
      title: `最低匹配分`,
    },
    acceptedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.decision = 'accepted'` }],
      title: `接受数`,
    },
    rejectedCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.decision = 'rejected'` }],
      title: `拒绝数`,
    },
    pendingCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.decision = 'pending'` }],
      title: `待定数`,
    },
    timeToDecisionHours: {
      sql: `EXTRACT(EPOCH FROM (decided_at - created_at)) / 3600`,
      type: `avg`,
      title: `平均决策时长 (h)`,
    },
  },

  preAggregations: {
    main: {
      type: `rollup`,
      measures: [count, avgScore, acceptedCount, rejectedCount],
      dimensions: [status, decision, channel, scoreBucket, agentId],
      refreshKey: { every: `5 minutes` },
    },
  },
});
