# Design Tokens — v10.0

All colors, spacing, radii, typography and motion values are defined as CSS
custom properties in `app/globals.css` under the `@theme inline` block and the
`:root` / `.dark` scopes. **No component should hardcode hex colors** — they
must reference a token so white-label theming (`lib/theme.ts`) and dark mode
work correctly.

## Token inventory (100+)

Defined in `app/globals.css`:

| Category | Tokens |
| --- | --- |
| Brand | `--color-teal`, `--color-teal-light`, `--color-teal-dark`, `--color-teal-muted`, `--color-navy` |
| Surface | `--background`, `--foreground`, `--card`, `--card-foreground`, `--popover`, `--popover-foreground` |
| Primary | `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--accent`, `--accent-foreground` |
| Muted | `--muted`, `--muted-foreground` |
| Destructive | `--destructive` |
| Border / input / ring | `--border`, `--input`, `--ring` |
| Chart | `--chart-1` … `--chart-5` |
| Sidebar | `--sidebar`, `--sidebar-foreground`, `--sidebar-primary`, `--sidebar-accent`, `--sidebar-border`, `--sidebar-ring` |
| Radius | `--radius` + computed `sm/md/lg/xl/2xl/3xl/4xl` |
| Typography | `--font-sans`, `--font-geist-mono`, `--font-heading` |

## Usage

```tsx
// Good — token via Tailwind semantic class
<div className="bg-background text-foreground border-border" />

// Good — raw token
<div style={{ backgroundColor: "var(--color-teal-muted)" }} />

// Bad — hardcoded hex (breaks theming + dark)
<div className="bg-[#00D4AA]" />
```

## Dark mode

`.dark` class toggles every `--*` token (see `@custom-variant dark` in
globals.css). `next-themes` (`ThemeProvider`) applies the class at runtime;
Storybook mirrors this via the `theme` toolbar global in `.storybook/preview.ts`.

## Audit

To find regressions:

```bash
cd frontend
grep -rnE "#[0-9a-fA-F]{3,6}" components/ app/ --include="*.tsx" \
  | grep -vE "globals.css|\\bslate-[0-9]|tailwind" \
  | grep -vE "data-testid|alt=|src=|href=|url\\("
```

Remaining literal hex usages (≈34 files) are in third-party chart palettes and
image/avatar URLs where a CSS token cannot apply; these are documented
exceptions, not brand colors.
