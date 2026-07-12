import type { Meta, StoryObj } from "@storybook/nextjs";
import { MatchCounterfactual } from "./MatchCounterfactual";

const meta: Meta<typeof MatchCounterfactual> = { title: "Match/MatchCounterfactual", component: MatchCounterfactual, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof MatchCounterfactual>;

export const Default: Story = {
  args: { scenario: "With 2 more years of backend experience, score would rise to 91" },
};
export const Missing: Story = { args: { scenario: "No counterfactual available" } };