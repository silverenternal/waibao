import type { StorybookConfig } from "@storybook/nextjs";

const config: StorybookConfig = {
  stories: [
    "../components/**/*.stories.@(ts|tsx|mdx)",
    "../components/**/*.mdx",
    "../app/**/*.stories.@(ts|tsx|mdx)",
    "../app/**/*.mdx",
  ],
  addons: [
    "@storybook/addon-a11y",
  ],
  framework: {
    name: "@storybook/nextjs",
    options: {},
  },
  typescript: {
    check: false,
    reactDocgen: "react-docgen-typescript",
  },
  docs: {
    autodocs: "tag",
  },
  staticDirs: ["../public"],
};

export default config;