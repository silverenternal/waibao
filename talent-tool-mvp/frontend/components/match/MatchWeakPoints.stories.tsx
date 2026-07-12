import type { Meta, StoryObj } from "@storybook/nextjs";
import { MatchWeakPoints } from "./MatchWeakPoints";

const meta: Meta<typeof MatchWeakPoints> = { title: "Match/MatchWeakPoints", component: MatchWeakPoints, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof MatchWeakPoints>;

export const Default: Story = { args: { weakPoints: ["Missing Kubernetes", "Less than 2 yrs leadership"] } };
export const None: Story = { args: { weakPoints: [] } };