# Storybook (T1607)

The Mothership frontend uses [Storybook 9](https://storybook.js.org/) to
document, develop, and visually regression-test its component library.

## Why Storybook

* **Living catalogue.** Every component lives next to a story, so
  designers and engineers can browse what exists without grepping the repo.
* **Visual review.** Reviewers can flip through components in isolation
  against light/dark backgrounds.
* **A11y checks.** `@storybook/addon-a11y` is enabled by default and runs
  axe-core against every rendered story.

## Quick start

```bash
cd frontend
pnpm install
pnpm storybook          # dev server on http://localhost:6006
pnpm build-storybook    # static build → frontend/storybook-static/
```

The static build is also produced on every CI run and uploaded as an
artifact (see `.github/workflows/storybook.yml`).

## Configuration

* `.storybook/main.ts` — registers story globs (`components/**/*.stories.tsx`
  and `app/**/*.stories.tsx`), the `@storybook/nextjs` framework, and the
  a11y addon.
* `.storybook/preview.ts` — loads `app/globals.css`, applies a centred
  layout, configures light/dark/muted backgrounds, and registers an `a11y`
  panel with the default rule set.

## Writing a story (CSF3)

```tsx
import type { Meta, StoryObj } from "@storybook/nextjs";
import { Button } from "./button";

const meta: Meta<typeof Button> = {
  title: "UI/Button",
  component: Button,
  tags: ["autodocs"],          // generates a Docs page
  argTypes: { variant: { control: "select", options: ["default", "outline"] } },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = { args: { children: "Save", variant: "default" } };
export const Outline: Story = { args: { children: "Cancel", variant: "outline" } };
```

### Conventions

* Title hierarchy mirrors the folder layout: `UI/...`, `Shared/...`,
  `Mind/...`, `Mothership/...`, `Match/...`, `Components/...`.
* Always include `tags: ["autodocs"]` so a Docs page is auto-generated.
* Use `argTypes` for any prop that benefits from a control (select,
  boolean, range).
* Stories should be deterministic — pass data inline, never fetch.

## CI

A dedicated GitHub Actions workflow (`.github/workflows/storybook.yml`)
builds Storybook on every push and PR.  The static output is uploaded as
an artifact named `storybook-static`.

## Catalogue cross-reference

See [docs/COMPONENTS.md](COMPONENTS.md) for the canonical index of every
component and where its story lives.