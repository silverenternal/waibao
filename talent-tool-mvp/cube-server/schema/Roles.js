// Cube.js schema — Roles (job positions) cube
// Drives the HR funnel, recruitment efficiency, and channel ROI dashboards.

cube(`Roles`, {
  sql: `SELECT * FROM roles`,

  joins: {
    Matches: {
      sql: `${CUBE}.id = ${Matches}.role_id`,
      relationship: `hasMany`,
    },
    Tickets: {
      sql: `${CUBE}.id = ${Tickets}.role_id`,
      relationship: `hasMany`,
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
    department: {
      sql: `department`,
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
    employmentType: {
      sql: `employment_type`,
      type: `string`,
    },
    remote: {
      sql: `is_remote`,
      type: `boolean`,
    },
    status: {
      sql: `status`,
      type: `string`,
    },
    urgency: {
      sql: `urgency`,
      type: `string`,
    },
    minSalary: {
      sql: `salary_min`,
      type: `number`,
    },
    maxSalary: {
      sql: `salary_max`,
      type: `number`,
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
      title: `岗位总数`,
    },
    openRoles: {
      type: `count`,
      filters: [{ sql: `${CUBE}.status = 'open'` }],
      title: `在招岗位`,
    },
    closedRoles: {
      type: `count`,
      filters: [{ sql: `${CUBE}.status = 'closed'` }],
      title: `已关闭岗位`,
    },
    avgMinSalary: {
      sql: `salary_min`,
      type: `avg`,
      title: `平均最低薪资`,
    },
    avgMaxSalary: {
      sql: `salary_max`,
      type: `avg`,
      title: `平均最高薪资`,
    },
    daysToFill: {
      sql: `EXTRACT(EPOCH FROM (closed_at - created_at)) / 86400`,
      type: `avg`,
      title: `平均填补天数`,
    },
    totalMatches: {
      sql: `${Matches}.id`,
      type: `count`,
      title: `匹配总数`,
    },
  },

  preAggregations: {
    main: {
      type: `rollup`,
      measures: [count, openRoles, closedRoles, daysToFill],
      dimensions: [department, city, seniority, status, urgency],
      refreshKey: { every: `5 minutes` },
    },
  },
});
