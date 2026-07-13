// T2703: Multi-Agent admin page types — mirror backend services.multiagent.

export type ScenarioKind =
  | "resume_scoring"
  | "bias_review"
  | "offer_negotiation"
  | "strategy_decode";

export type ConsensusStrategy =
  | "majority"
  | "unanimous"
  | "weighted"
  | "quorum";

export type CollaborationPattern =
  | "sequential"
  | "parallel"
  | "hierarchical"
  | "debate";

export interface AgentOutput {
  agent_id: string;
  agent_goal: string;
  task: string;
  decision: unknown;
  confidence: number;
  rationale: string;
  ts: number;
}

export interface ConsensusVote {
  agent_id: string;
  decision: unknown;
  confidence: number;
  weight: number;
  rationale: string;
}

export interface ConsensusResult {
  strategy: ConsensusStrategy;
  decision: unknown;
  confidence: number;
  votes: ConsensusVote[];
  tally: Record<string, number>;
  reached: boolean;
  notes: string;
}

export interface StepPlan {
  role: {
    kind: string;
    title: string;
    goal: string;
    backstory: string;
  };
  agent_id?: string | null;
  description: string;
  expected_output_keys: string[];
  weight: number;
}

export interface PatternPlan {
  scenario: ScenarioKind;
  pattern: CollaborationPattern;
  consensus: ConsensusStrategy;
  max_rounds: number;
  description: string;
  steps: StepPlan[];
}

export interface CrewAgent {
  role: string;
  goal: string;
  backstory: string;
  tools: string[];
  allow_delegation: boolean;
}

export interface OrchestrationResult {
  run_id: string;
  task: {
    scenario: ScenarioKind;
    goal: string;
    pattern?: CollaborationPattern | null;
    consensus?: ConsensusStrategy | null;
    max_rounds: number;
  };
  crew: {
    agents: CrewAgent[];
    tasks: unknown[];
    process: string;
  };
  pattern: PatternPlan;
  consensus: ConsensusResult;
  rounds: number;
  status: "completed" | "failed" | "no_consensus";
  outputs: Record<string, AgentOutput>;
  started_at: number;
  finished_at?: number | null;
  error?: string | null;
}

export const SCENARIO_LABEL: Record<ScenarioKind, string> = {
  resume_scoring: "Resume Scoring",
  bias_review: "Bias Review",
  offer_negotiation: "Offer Negotiation",
  strategy_decode: "Strategy Decode",
};

export const SCENARIO_DESCRIPTION: Record<ScenarioKind, string> = {
  resume_scoring:
    "3 screeners (Tech / Culture / Domain) independently score a resume; weighted vote picks the final score.",
  bias_review:
    "Writer drafts, Bias Reviewer challenges, then revises until approved.",
  offer_negotiation:
    "Researcher gathers market data, Writer drafts offer, Reviewer signs off.",
  strategy_decode:
    "PM decomposes the strategic question, delegates to specialists, then aggregates a final review.",
};