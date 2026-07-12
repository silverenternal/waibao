import type { Meta, StoryObj } from "@storybook/nextjs";
import { ScoringBreakdown } from "./scoring-breakdown";

const meta: Meta<typeof ScoringBreakdown> = { title: "Mothership/ScoringBreakdown", component: ScoringBreakdown, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ScoringBreakdown>;

export const Default: Story = { args: { structured: 0.85, semantic: 0.78, experience: 0.9 } };
export const LowSemantic: Story = { args: { structured: 0.6, semantic: 0.2, experience: 0.5 } };