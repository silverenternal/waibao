/**
 * v9.1 — Jobseeker shared subcomponents barrel export.
 *
 * Re-exports: CareCard, QuickActions, AIRecommendations,
 * ProactiveBanner, PersonalityBadge (+ PersonalityBadgeGroup).
 *
 * Each component is strongly-typed, generic over its props (no hard-coded
 * tenant/i18n values), responsive, and accessible. Stories live next to the
 * components as `*.stories.tsx`.
 */

export { CareCard, default as CareCardDefault } from "./CareCard";
export type { CareCardItem, CareCardProps, CareCardTone } from "./CareCard";

export {
  QuickActions,
  default as QuickActionsDefault,
} from "./QuickActions";
export type { QuickAction, QuickActionsProps } from "./QuickActions";

export {
  AIRecommendations,
  default as AIRecommendationsDefault,
} from "./AIRecommendations";
export type {
  AIRecommendation,
  AIRecommendationsProps,
  RecommendationTone,
} from "./AIRecommendations";

export {
  ProactiveBanner,
  default as ProactiveBannerDefault,
} from "./ProactiveBanner";
export type {
  ProactiveBannerProps,
  ProactiveBannerTone,
} from "./ProactiveBanner";

export {
  PersonalityBadge,
  PersonalityBadgeGroup,
  default as PersonalityBadgeDefault,
} from "./PersonalityBadge";
export type {
  PersonalityBadgeGroupProps,
  PersonalityBadgeProps,
  PersonalityTone,
  PersonalityTrait,
} from "./PersonalityBadge";
