import type { Meta, StoryObj } from "@storybook/nextjs";
import { ConfidenceBadge } from "./confidence-badge";

const meta: Meta<typeof ConfidenceBadge> = { title: "Shared/ConfidenceBadge", component: ConfidenceBadge, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ConfidenceBadge>;

export const High: Story = { args: { score: 0.95 } };
export const Medium: Story = { args: { score: 0.7 } };
export const Low: Story = { args: { score: 0.4 } };