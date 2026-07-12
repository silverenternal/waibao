-- v6.0 T2105 — Agent Composition migration
-- Adds: workflows, workflow_runs, workflow_run_steps tables.
-- A workflow stores a DAG definition (nodes/edges/variables) as JSONB;
-- a workflow_run captures a single execution's lifecycle and per-step traces.

-- ---------------------------------------------------------------------------
-- workflows — declarative DAG definitions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workflows (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    definition  JSONB NOT NULL DEFAULT '{}'::jsonb,
    version     TEXT NOT NULL DEFAULT '1.0',
    is_template BOOLEAN NOT NULL DEFAULT FALSE,
    category    TEXT,
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflows_name ON public.workflows(name);
CREATE INDEX IF NOT EXISTS idx_workflows_category ON public.workflows(category);
CREATE INDEX IF NOT EXISTS idx_workflows_is_template ON public.workflows(is_template);

COMMENT ON TABLE public.workflows IS
    'Agent Composition workflows: declarative DAG (nodes/edges/variables) persisted as JSONB.';

-- ---------------------------------------------------------------------------
-- workflow_runs — single execution lifecycle
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workflow_runs (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL UNIQUE,
    workflow_id BIGINT NOT NULL REFERENCES public.workflows(id) ON DELETE CASCADE,
    workflow_name TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'paused',
                                      'completed', 'failed', 'cancelled')),
    input       JSONB,
    output      JSONB,
    variables   JSONB NOT NULL DEFAULT '{}'::jsonb,
    nodes_executed JSONB NOT NULL DEFAULT '[]'::jsonb,
    paused_at_node TEXT,
    error       TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id
    ON public.workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
    ON public.workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at
    ON public.workflow_runs(started_at DESC);

COMMENT ON TABLE public.workflow_runs IS
    'A workflow execution: status, input/output, variables and node-execution history.';

-- ---------------------------------------------------------------------------
-- workflow_run_steps — per-node execution traces
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workflow_run_steps (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    workflow_id BIGINT REFERENCES public.workflows(id) ON DELETE CASCADE,
    node_id     TEXT NOT NULL,
    node_type   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed',
                                      'paused', 'skipped')),
    input       JSONB,
    output      JSONB,
    error       TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run_id
    ON public.workflow_run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_status
    ON public.workflow_run_steps(status);

COMMENT ON TABLE public.workflow_run_steps IS
    'Per-node traces for a workflow run: timing, input/output and error state.';

-- ---------------------------------------------------------------------------
-- updated_at trigger for workflows
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trg_workflows_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_workflows_updated_at ON public.workflows;
CREATE TRIGGER trg_workflows_updated_at
    BEFORE UPDATE ON public.workflows
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_workflows_updated_at();