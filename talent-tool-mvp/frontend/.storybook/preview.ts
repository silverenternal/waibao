import type { Preview } from "@storybook/nextjs";
import { useEffect, useGlobals } from "@storybook/preview-api";
import * as React from "react";
import "../app/globals.css";

/**
 * Dark-mode toolbar integration.
 *
 * Adds a "theme" global (light/dark/system) toggled from the Storybook
 * toolbar. The decorator applies the `dark` class to <html> so the
 * `@custom-variant dark (&:is(.dark *))` rule in globals.css activates —
 * the same mechanism next-themes uses in the app. This lets every story
 * be reviewed in true dark mode and surfaces contrast regressions.
 */
const withThemeProvider = (StoryFn: React.ComponentType) => {
  const [globals] = useGlobals();
  const theme = globals.theme || "system";
  React.useEffect(() => {
    const root = document.documentElement;
    const apply = (mode: "light" | "dark") => {
      root.classList.toggle("dark", mode === "dark");
      root.style.colorScheme = mode;
    };
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      apply(mq.matches ? "dark" : "light");
      const handler = (e: MediaQueryListEvent) =>
        apply(e.matches ? "dark" : "light");
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
    apply(theme as "light" | "dark");
  }, [theme]);
  return <StoryFn />;
};

const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: "^on[A-Z].*" },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    layout: "centered",
    backgrounds: {
      default: "light",
      values: [
        { name: "light", value: "#ffffff" },
        { name: "dark", value: "#0a0a0a" },
        { name: "muted", value: "#f4f4f5" },
      ],
    },
    a11y: {
      // 'todo' | 'error' | 'warn' | 'off' — show violations but don't block dev
      config: {
        rules: [
          { id: "color-contrast", enabled: true },
          { id: "label", enabled: true },
          { id: "button-name", enabled: true },
          { id: "tabindex", enabled: true },
          { id: "aria-valid-attr", enabled: true },
          { id: "aria-required-attr", enabled: true },
        ],
      },
      options: {
        checks: { "color-contrast": { isParameterizable: false } },
      },
    },
  },
  globalTypes: {
    theme: {
      name: "Theme",
      description: "Light / Dark / System",
      defaultValue: "system",
      toolbar: {
        icon: "circlehollow",
        items: [
          { value: "light", icon: "sun", title: "Light" },
          { value: "dark", icon: "moon", title: "Dark" },
          { value: "system", icon: "browser", title: "System" },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [
    withThemeProvider,
    (Story) => (
      <div className="p-4 w-full max-w-2xl">
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
};

export default preview;
