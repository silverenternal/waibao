"use client";

/** @file Storybook stories for the Support widget. */
import type { Meta, StoryObj } from "@storybook/react";
import { SupportWidget } from "./SupportWidget";

const meta = {
  title: "Support/SupportWidget",
  component: SupportWidget,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof SupportWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Closed: Story = {
  args: {},
};

export const WithErrorLog: Story = {
  args: {
    initialErrorLog: "Error: stream connection reset (sse.connect retries exceeded)",
    defaultTags: ["feature:realtime", "page:/agents/realtime"],
  },
};
