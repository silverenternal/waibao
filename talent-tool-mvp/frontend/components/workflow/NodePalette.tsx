"use client";

/**
 * v6.0 T2105 — Node palette.
 *
 * The palette lists every node type that can be dropped onto the canvas:
 *   - 6 trigger nodes (one per EventBus event)
 *   - 16 agent nodes (the platform's full agent roster)
 *   - 8 action nodes (email/ticket/db_write/event + variants)
 *   - plus the structural nodes (condition, delay, human).
 *
 * Drag-and-drop is implemented natively via HTML5 data transfer so the
 * project avoids taking on a heavy react-flow dependency.
 */

import * as React from "react";

import type { NodeType } from "./types";

interface PaletteItem {
  type: NodeType | "trigger-event";
  label: string;
  description: string;
  /** Default config payload when the node is dropped onto the canvas. */
  defaults: Record<string, unknown>;
  category: "Trigger" | "Agent" | "Condition" | "Action" | "Delay" | "Human";
  /** Trigger events are special — they encode a sub-event in their config. */
  event?: string;
}

const TRIGGERS: PaletteItem[] = [
  { type: "trigger-event", label: "candidate.applied",
    description: "When a candidate submits an application",
    defaults: { event: "candidate.applied" }, category: "Trigger",
    event: "candidate.applied" },
  { type: "trigger-event", label: "resume.uploaded",
    description: "A new resume lands in storage",
    defaults: { event: "resume.uploaded" }, category: "Trigger",
    event: "resume.uploaded" },
  { type: "trigger-event", label: "employee.hired",
    description: "New hire accepted an offer",
    defaults: { event: "employee.hired" }, category: "Trigger",
    event: "employee.hired" },
  { type: "trigger-event", label: "ticket.created",
    description: "A support ticket is opened",
    defaults: { event: "ticket.created" }, category: "Trigger",
    event: "ticket.created" },
  { type: "trigger-event", label: "vision.submitted",
    description: "Hiring-manager vision document submitted",
    defaults: { event: "vision.submitted" }, category: "Trigger",
    event: "vision.submitted" },
  { type: "trigger-event", label: "strategy.submitted",
    description: "Strategy doc submitted for review",
    defaults: { event: "strategy.submitted" }, category: "Trigger",
    event: "strategy.submitted" },
  { type: "trigger-event", label: "interview.completed",
    description: "An AI / live interview finishes",
    defaults: { event: "interview.completed" }, category: "Trigger",
    event: "interview.completed" },
  { type: "trigger-event", label: "offer.accepted",
    description: "Candidate accepts the offer",
    defaults: { event: "offer.accepted" }, category: "Trigger",
    event: "offer.accepted" },
];

const AGENTS: PaletteItem[] = [
  { type: "agent", label: "intake_agent",
    description: "Capture structured intake from free-form text",
    defaults: { agent: "intake_agent" }, category: "Agent" },
  { type: "agent", label: "clarifier_agent",
    description: "Follow-up Q&A when requirements are unclear",
    defaults: { agent: "clarifier_agent" }, category: "Agent" },
  { type: "agent", label: "profile_agent",
    description: "Maintain jobseeker profile state",
    defaults: { agent: "profile_agent" }, category: "Agent" },
  { type: "agent", label: "career_planner_agent",
    description: "Long-term career path planning",
    defaults: { agent: "career_planner_agent" }, category: "Agent" },
  { type: "agent", label: "emotion_agent",
    description: "Detect candidate emotion signals",
    defaults: { agent: "emotion_agent" }, category: "Agent" },
  { type: "agent", label: "daily_journal_agent",
    description: "Daily journal / reflection prompt",
    defaults: { agent: "daily_journal_agent" }, category: "Agent" },
  { type: "agent", label: "job_spec_agent",
    description: "Convert JD to structured spec",
    defaults: { agent: "job_spec_agent" }, category: "Agent" },
  { type: "agent", label: "talent_brief_agent",
    description: "Generate talent brief from JD",
    defaults: { agent: "talent_brief_agent" }, category: "Agent" },
  { type: "agent", label: "vision_agent",
    description: "Hiring-manager vision draft",
    defaults: { agent: "vision_agent" }, category: "Agent" },
  { type: "agent", label: "policy_agent",
    description: "Compliance & policy review",
    defaults: { agent: "policy_agent" }, category: "Agent" },
  { type: "agent", label: "hr_service_agent",
    description: "Internal HR service assistant",
    defaults: { agent: "hr_service_agent" }, category: "Agent" },
  { type: "agent", label: "compliance_agent",
    description: "Bias / fairness reviewer",
    defaults: { agent: "compliance_agent" }, category: "Agent" },
  { type: "agent", label: "persona_agent",
    description: "Persona preferences / escalation",
    defaults: { agent: "persona_agent" }, category: "Agent" },
  { type: "agent", label: "multi_party_agent",
    description: "Multi-party coordination",
    defaults: { agent: "multi_party_agent" }, category: "Agent" },
  { type: "agent", label: "employer_clarifier_agent",
    description: "Follow-up Q&A for hiring managers",
    defaults: { agent: "employer_clarifier_agent" }, category: "Agent" },
  { type: "agent", label: "mutual_evaluator",
    description: "Compare candidate vs. role",
    defaults: { agent: "mutual_evaluator" }, category: "Agent" },
];

const ACTIONS: PaletteItem[] = [
  { type: "action", label: "Send email",
    description: "Notify a user via email",
    defaults: { kind: "email",
                params: { to: "$recipient", subject: "", body: "" } },
    category: "Action" },
  { type: "action", label: "Create ticket",
    description: "Open a support ticket",
    defaults: { kind: "ticket",
                params: { queue: "general", priority: "normal" } },
    category: "Action" },
  { type: "action", label: "DB write",
    description: "Persist a row via the platform store",
    defaults: { kind: "db_write", params: { table: "", row: {} } },
    category: "Action" },
  { type: "action", label: "Emit event",
    description: "Fan out via the EventBus",
    defaults: { kind: "event", event: "workflow.custom", params: {} },
    category: "Action" },
];

const STRUCTURAL: PaletteItem[] = [
  { type: "condition", label: "Condition",
    description: "Branch via expression",
    defaults: { expression: "1 == 1" }, category: "Condition" },
  { type: "delay", label: "Delay",
    description: "Wait N seconds",
    defaults: { seconds: 0 }, category: "Delay" },
  { type: "human", label: "Human approval",
    description: "Pause until a human decides",
    defaults: { reason: "Needs human approval" }, category: "Human" },
];

const CATEGORIES: PaletteItem["category"][] = [
  "Trigger", "Agent", "Condition", "Action", "Delay", "Human",
];

interface NodePaletteProps {
  onAddTrigger?: (eventName: string) => void;
}

export function NodePalette(props: NodePaletteProps): JSX.Element {
  const grouped = React.useMemo(() => {
    const buckets: Record<string, PaletteItem[]> = {};
    const all = [...TRIGGERS, ...AGENTS, ...ACTIONS, ...STRUCTURAL];
    for (const item of all) {
      (buckets[item.category] ||= []).push(item);
    }
    return buckets;
  }, []);

  const handleDragStart = (
    e: React.DragEvent<HTMLDivElement>,
    item: PaletteItem,
  ) => {
    e.dataTransfer.setData("application/x-workflow-node",
                            JSON.stringify(item));
    e.dataTransfer.effectAllowed = "copy";
  };

  return (
    <aside className="flex h-full w-72 flex-col gap-3 overflow-y-auto border-r bg-slate-50 p-3 text-sm">
      <h3 className="font-semibold text-slate-700">Nodes</h3>
      {CATEGORIES.map((cat) => (
        <section key={cat}>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
            {cat}s
          </h4>
          <div className="flex flex-col gap-1">
            {(grouped[cat] || []).map((item) => (
              <div
                key={`${cat}-${item.label}`}
                draggable
                onDragStart={(e) => handleDragStart(e, item)}
                onDoubleClick={() => {
                  if (item.type === "trigger-event" && item.event &&
                      props.onAddTrigger) {
                    props.onAddTrigger(item.event);
                  }
                }}
                className="cursor-grab rounded border border-slate-200 bg-white px-2 py-1.5 shadow-sm hover:border-indigo-400 hover:shadow"
                data-testid={`palette-${item.label}`}
              >
                <div className="font-medium text-slate-800">{item.label}</div>
                <div className="text-[11px] text-slate-500">
                  {item.description}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </aside>
  );
}

export const PALETTE_AGENTS = AGENTS.map((a) => a.label);
export const PALETTE_TRIGGERS = TRIGGERS.map((t) => t.label);
export const PALETTE_ACTIONS = ACTIONS.map((a) => a.label);