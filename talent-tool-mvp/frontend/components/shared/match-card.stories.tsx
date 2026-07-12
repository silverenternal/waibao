import type { Meta, StoryObj } from "@storybook/nextjs";
import { MatchCard } from "./match-card";

const meta: Meta<typeof MatchCard> = {
  title: "Shared/MatchCard",
  component: MatchCard,
  tags: ["autodocs"],
};
export default meta;
type Story = StoryObj<typeof MatchCard>;

export const HighMatch: Story = {
  args: { role: "Senior Designer", candidate: "Sarah Lee", score: 94, reasons: ["8 yrs design systems", "Figma expertise"] },
};
export const MediumMatch: Story = {
  args: { role: "Product Manager", candidate: "John Park", score: 71, reasons: ["Cross-functional experience"] },
};
export const LowMatch: Story = {
  args: { role: "ML Engineer", candidate: "Anna Sun", score: 42, reasons: ["Limited ML background"] },
};