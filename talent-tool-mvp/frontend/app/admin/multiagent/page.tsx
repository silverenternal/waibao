"use client";

/**
 * T2703: Multi-Agent (CrewAI vendor-in) admin monitor page.
 *
 * Live UI for running one of the 4 core scenarios end-to-end and
 * watching each agent's output, votes, and the consensus result.
 */

import * as React from "react";

import {
  CollaborationPattern,
  ConsensusStrategy,
  OrchestrationResult,
  SCENARIO_DESCRIPTION,
  SCENARIO_LABEL,
  ScenarioKind,
} from "@/components/multiagent/types";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  if (r.status === 204) return null as unknown as T;
  return r.json();
}

const SCENARIOS: ScenarioKind[] = [
  "resume_scoring",
  "bias_review",
  "offer_negotiation",
  "strategy_decode",
];

const CONSENSUS_OPTIONS: ConsensusStrategy[] = [
  "majority",
  "unanimous",
  "weighted",
  "quorum",
];

const PATTERN_OPTIONS: CollaborationPattern[] = [
  "sequential",
  "parallel",
  "hierarchical",
  "debate",
];

export default function MultiAgentAdminPage(): React.JSX.Element {
  const [scenario, setScenario] = React.useState<ScenarioKind>("resume_scoring");
  const [goal, setGoal] = React.useState("Score a senior backend engineer resume");
  const [pattern, setPattern] = React.useState<CollaborationPattern | "">("");
  const [consensus, setConsensus] = React.useState<ConsensusStrategy | "">("");
  const [maxRounds, setMaxRounds] = React.useState(3);

  const [result, setResult] = React.useState<OrchestrationResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [history, setHistory] = React.useState<OrchestrationResult[]>([]);

  const run = React.useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        scenario,
        goal,
        max_rounds: maxRounds,
      };
      if (pattern) body.pattern = pattern;
      if (consensus) body.consensus = consensus;
      const res = await api<OrchestrationResult>(`/api/multiagent/run`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(res);
      setHistory((prev) => [res, ...prev].slice(0, 10));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [scenario, goal, pattern, consensus, maxRounds]);

  return (
    <main className="mx-auto max-w-7xl p-6 space-y-6">
      <header>
        <h1 className="text-3xl font-semibold">Multi-Agent Orchestration</h1>
        <p className="text-sm text-muted-foreground mt-1">
          CrewAI vendor-in. Run one of the 4 core scenarios and inspect each
          agent&apos;s output, vote tally, and consensus decision in real time.
        </p>
      </header>

      {/* Scenario picker */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {SCENARIOS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setScenario(s)}
            className={`text-left p-3 rounded-md border transition ${
              scenario === s
                ? "border-primary bg-primary/5"
                : "hover:border-primary/40"
            }`}
          >
            <div className="font-medium">{SCENARIO_LABEL[s]}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {SCENARIO_DESCRIPTION[s]}
            </div>
          </button>
        ))}
      </section>

      {/* Controls */}
      <section className="rounded-md border p-4 grid grid-cols-1 md:grid-cols-4 gap-3">
        <label className="text-sm md:col-span-2">
          <span className="block font-medium mb-1">Goal</span>
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium mb-1">Pattern (override)</span>
          <select
            value={pattern}
            onChange={(e) => setPattern(e.target.value as CollaborationPattern)}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          >
            <option value="">— default —</option>
            {PATTERN_OPTIONS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block font-medium mb-1">Consensus</span>
          <select
            value={consensus}
            onChange={(e) => setConsensus(e.target.value as ConsensusStrategy)}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          >
            <option value="">— default —</option>
            {CONSENSUS_OPTIONS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block font-medium mb-1">Max rounds</span>
          <input
            type="number"
            min={1}
            max={10}
            value={maxRounds}
            onChange={(e) => setMaxRounds(Number(e.target.value) || 1)}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </label>
        <div className="md:col-span-3 flex items-end justify-end">
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Running…" : "Run scenario"}
          </button>
        </div>
      </section>

      {error && (
        <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm">
          {error}
        </div>
      )}

      {result && <RunReport result={result} />}

      {history.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Recent runs</h2>
          <ul className="rounded-md border divide-y">
            {history.map((r) => (
              <li
                key={r.run_id}
                className="px-3 py-2 text-xs flex justify-between"
              >
                <span>{SCENARIO_LABEL[r.task.scenario]} — {r.task.goal}</span>
                <span className="font-mono">{r.status}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

function RunReport({ result }: { result: OrchestrationResult }): React.JSX.Element {
  return (
    <section className="space-y-4">
      <div className="rounded-md border p-4 grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
        <Stat label="Run id" value={result.run_id.slice(0, 8)} />
        <Stat label="Status" value={result.status} />
        <Stat label="Rounds" value={String(result.rounds)} />
        <Stat
          label="Consensus reached"
          value={result.consensus.reached ? "yes" : "no"}
        />
      </div>

      <div className="rounded-md border p-4 space-y-3">
        <h2 className="text-lg font-semibold">Plan</h2>
        <p className="text-xs text-muted-foreground">{result.pattern.description}</p>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>scenario: {result.pattern.scenario}</Badge>
          <Badge>pattern: {result.pattern.pattern}</Badge>
          <Badge>consensus: {result.pattern.consensus}</Badge>
          <Badge>rounds: {result.pattern.max_rounds}</Badge>
        </div>
        <ul className="divide-y text-sm">
          {result.pattern.steps.map((s, i) => (
            <li key={i} className="py-2 flex justify-between">
              <span>
                <span className="font-medium">{s.role.title}</span>
                <span className="text-muted-foreground ml-2">
                  ({s.description})
                </span>
              </span>
              <span className="text-xs text-muted-foreground">
                weight: {s.weight}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-md border p-4 space-y-3">
        <h2 className="text-lg font-semibold">Agent outputs</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(result.outputs).map(([role, out]) => (
            <div key={role} className="rounded border bg-muted/30 p-3 text-xs">
              <div className="font-medium mb-1">{role}</div>
              <pre className="whitespace-pre-wrap break-words">
{JSON.stringify(out, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-md border p-4 space-y-3">
        <h2 className="text-lg font-semibold">Consensus</h2>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>strategy: {result.consensus.strategy}</Badge>
          <Badge>reached: {String(result.consensus.reached)}</Badge>
          <Badge>confidence: {result.consensus.confidence.toFixed(2)}</Badge>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Decision</div>
          <pre className="rounded bg-muted/40 p-2 text-xs whitespace-pre-wrap">
{JSON.stringify(result.consensus.decision, null, 2)}
          </pre>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Tally</div>
          <table className="w-full text-xs">
            <tbody>
              {Object.entries(result.consensus.tally).map(([k, v]) => (
                <tr key={k} className="border-t">
                  <td className="py-1 pr-2 font-mono">{k}</td>
                  <td className="py-1 text-right">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Votes</div>
          <table className="w-full text-xs">
            <thead className="text-left">
              <tr>
                <th className="py-1 pr-2">Agent</th>
                <th className="py-1 pr-2">Decision</th>
                <th className="py-1 pr-2">Conf</th>
                <th className="py-1 pr-2">Weight</th>
              </tr>
            </thead>
            <tbody>
              {result.consensus.votes.map((v, i) => (
                <tr key={i} className="border-t">
                  <td className="py-1 pr-2">{v.agent_id}</td>
                  <td className="py-1 pr-2 font-mono">
                    {JSON.stringify(v.decision)}
                  </td>
                  <td className="py-1 pr-2">{v.confidence.toFixed(2)}</td>
                  <td className="py-1 pr-2">{v.weight}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {result.error && (
          <div className="rounded bg-destructive/10 text-destructive p-2 text-xs">
            {result.error}
          </div>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <span className="px-2 py-0.5 rounded bg-secondary text-secondary-foreground">
      {children}
    </span>
  );
}