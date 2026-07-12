export type {
  SeniorityLevel,
  AvailabilityStatus,
  RemotePolicy,
  RoleStatus,
  MatchStatus,
  ConfidenceLevel,
  HandoffStatus,
  QuoteStatus,
  Visibility,
  UserRole,
  SignalType,
  ExtractedSkill,
  RequiredSkill,
  ExperienceEntry,
  SalaryRange,
  SkillMatch,
  CandidateSource,
  CandidateCreate,
  Candidate,
  CandidateAnonymized,
  RoleCreate,
  Role,
  Match,
  SignalCreate,
  Signal,
  HandoffCreate,
  Handoff,
  QuoteRequest,
  Quote,
  CollectionCreate,
  Collection,
  Organisation,
  User,
} from "@/contracts/canonical";

// =============================================================
// T1303: Recruitment funnel + channel ROI analytics
// =============================================================

export interface FunnelStageMetric {
  stage: string;
  candidates: number;
  events: number;
}

export interface FunnelResponse {
  org_id: string | null;
  since_days: number;
  period_start: string;
  period_end: string;
  total_candidates: number;
  stages: { stage: string; candidates: number; events: number }[];
  conversion_rates: Record<string, number>;
  by_source: Record<string, Record<string, number>>;
  overall_conversion: number;
}

export interface FunnelStagesResponse {
  stages: FunnelStageMetric[];
  conversion_rates: Record<string, number>;
  overall_conversion: number;
  total_candidates: number;
  since_days: number;
  period_start: string;
  period_end: string;
}

export interface ChannelAttribution {
  channel: string;
  model: string;
  candidates: number;
  hires: number;
  hire_credit: number;
  cost_cents: number;
  revenue_cents: number;
  roi: number;
  cost_per_hire: number;
}

export interface ChannelAttributionResponse {
  model: string;
  channels: ChannelAttribution[];
  best_channel: string | null;
}

export interface ChannelRoiReport {
  org_id: string | null;
  since_days: number;
  period_start: string;
  period_end: string;
  by_model: Record<string, ChannelAttribution[]>;
  best_channel_by_model: Record<string, string>;
  summary: Record<string, { channels: number; total_hires: number; total_cost_cents: number; total_revenue_cents: number; avg_roi: number }>;
}

// =============================================================
// T1304: Job subscriptions + candidate recommendations
// =============================================================

export interface SubscriptionCriteria {
  role?: string;
  city?: string;
  salary_min?: number;
  currency?: string;
  skills?: string[];
  seniority?: string;
  remote_policy?: string;
}

export interface Subscription {
  id: string;
  user_id: string;
  name: string;
  criteria: SubscriptionCriteria;
  channels: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionBody {
  name: string;
  criteria: SubscriptionCriteria;
  channels: string[];
}

export interface JobMatch {
  id: string;
  title: string;
  company: string;
  city: string;
  salary_min: number;
  salary_max: number;
  currency: string;
  skills: string[];
  seniority: string;
  remote_policy: string;
  score: number;
  reasons: string[];
}

export interface RecommendedCandidate {
  candidate_id: string;
  full_name: string;
  headline: string;
  city: string;
  seniority: string;
  skills: string[];
  years_experience: number;
  overall_score: number;
  structured_score: number;
  semantic_score: number;
  experience_score: number;
  confidence: string;
  reasons: string[];
  missing_skills: string[];
}
