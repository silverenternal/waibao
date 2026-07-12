import type { Preview } from "@storybook/nextjs";
import "../app/globals.css";

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
        ],
      },
      options: {
        checks: { "color-contrast": { isParameterizable: false } },
      },
    },
  },
  decorators: [
    (Story) => (
      <div className="p-4">
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
};

export default preview;