import type { Meta, StoryObj } from "@storybook/nextjs";
import { MatchReason } from "./MatchReason";

const meta: Meta<typeof MatchReason> = { title: "Match/MatchReason", component: MatchReason, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof MatchReason>;

export const Strong: Story = { args: { reason: "Direct design systems experience", weight: 0.9 } };
export const Weak: Story = { args: { reason: "Some overlap with required stack", weight: 0.3 } };