import type { Meta, StoryObj } from "@storybook/nextjs";
import { ConsensusScore } from "./ConsensusScore";

const meta: Meta<typeof ConsensusScore> = { title: "Mothership/ConsensusScore", component: ConsensusScore, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ConsensusScore>;

export const Default: Story = { args: { score: 88 } };
export const Low: Story = { args: { score: 41 } };