# Onboarding Design — T1403

> Optimised for first-time activation. Mobile + desktop ready. Keyboard accessible.

## Goals

1. **First-time activation < 90s.** A user who lands on the dashboard for the first time should reach their first value moment (a match, a recommended action) within 90 seconds.
2. **Persistent but unobtrusive.** The onboarding checklist survives across sessions via `localStorage`, but never blocks core navigation.
3. **Accessible by default.** WCAG 2.1 AA compliant: full keyboard traversal, focus management, screen-reader narration of step progress.

## Components

| Component | Purpose | Where |
|-----------|---------|-------|
| `ProductTour.tsx` | Spotlight + tooltip, keyboard navigable | High-level tour |
| `OnboardingChecklist.tsx` | Persistent 4-step checklist | Sidebar of dashboards & welcome pages |
| `use-onboarding.ts` | State hook (persisted) | All callers |
| `OnboardingChecklist` "mark step" | User-controlled progression | Every checklist item |

## Tour Design Principles

### 1. Spotlight & tooltip, not modal

The tour uses a non-blocking spotlight pattern (box-shadow mask) around each target. The rest of the page remains visible so the user sees the actual product. The tooltip is a floating card with a clear pointer back to the highlighted element.

### 2. Keyboard-first

```
Esc          Close the tour
→ / Space    Next step
←            Previous step
Home         First step
End          Last step
Enter        Activate focused CTA (Next/Finish)
Tab          Move within trap (focus stays on tooltip + close button)
```

The tooltip is `role="dialog"` `aria-modal="true"` with `aria-labelledby` (title) and `aria-describedby` (body). The current step indicator (`1 / 4`) is announced via `aria-live="polite"`.

### 3. Mobile-friendly

On viewports `<640px`, the tooltip docks to the bottom of the screen instead of trying to float near the spotlight. This avoids off-screen tooltips and cramped placement near hamburger menus.

### 4. Auto-trigger only once

The tour is fired on dashboard mount when `localStorage.getItem('wb_product_tour_done') !== '1'`. After completion (or explicit close), the flag is set. The user can replay via "重新播放产品导览".

### 5. Steps are short, value-focused

Each tour step covers a single atomic value moment — for the jobseeker, "AI matching", "your profile", "your inbox". Each step's body copy is < 140 chars.

## Onboarding Checklist (4 steps)

Both jobseeker and employer tracks share the same structure: profile → first value → first collaboration → invite team.

| Step | Jobseeker | Employer |
|------|-----------|----------|
| 1 | 完善个人档案 | 完善公司档案 |
| 2 | 查看第一次 AI 匹配 | 查看候选人匹配 |
| 3 | 发起一次约谈 | 完成一次 handoff |
| 4 | 邀请朋友 (可选) | 邀请同事 (可选) |

State is persisted to `localStorage` under `wb_onboarding_progress` with `completed: OnboardingStep[]` and `dismissed: boolean`.

```ts
OnboardingStep =
  | "profile_complete"
  | "first_match_viewed"
  | "first_handoff_created"
  | "first_teammate_invited";
```

## Metrics

Track in production:
- % of new users who complete the tour (`wb_product_tour_done` set within 24h)
- % of new users who reach step N (1..4)
- Median time from sign-up to first completion
- Drop-off step (last incomplete step)

## Files

- `frontend/components/ProductTour.tsx`
- `frontend/components/OnboardingChecklist.tsx`
- `frontend/hooks/use-onboarding.ts`
- `frontend/app/(jobseeker)/dashboard/page.tsx`
- `frontend/app/(employer)/dashboard/page.tsx`
- `frontend/app/(jobseeker)/onboarding/welcome/page.tsx`
- `frontend/app/(employer)/onboarding/welcome/page.tsx`

## Future

- Server-side persistence (e.g. `onboarding_progress` table) so users switching devices see the same checklist state.
- A/B variants: short tour (3 steps) vs. long tour (5 steps).
- Auto-skip steps that are already complete (e.g. profile already 100%).
