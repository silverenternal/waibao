import type { Meta, StoryObj } from "@storybook/nextjs";
import { EmptyState } from "./empty-state";

const meta: Meta<typeof EmptyState> = { title: "Shared/EmptyState", component: EmptyState, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EmptyState>;

export const Default: Story = {
  args: { title: "No candidates yet", description: "Upload a CV to get started.", actionLabel: "Upload CV" },
};
export const Minimal: Story = { args: { title: "Nothing here" } };