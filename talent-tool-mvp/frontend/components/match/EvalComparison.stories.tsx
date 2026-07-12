import type { Meta, StoryObj } from "@storybook/nextjs";
import { EvalComparison } from "./EvalComparison";

const meta: Meta<typeof EvalComparison> = { title: "Match/EvalComparison", component: EvalComparison, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EvalComparison>;

export const Default: Story = {
  args: {
    candidateScore: 88,
    employerScore: 75,
    consensus: 81,
  },
};