import type { Meta, StoryObj } from "@storybook/nextjs";
import { ActionCard } from "./action-card";

const meta: Meta<typeof ActionCard> = { title: "Shared/ActionCard", component: ActionCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ActionCard>;

export const Default: Story = {
  args: { title: "Review shortlisted", description: "12 candidates need your review.", actionLabel: "Review now" },
};
export const Urgent: Story = {
  args: { title: "Offer expiring", description: "Offer to Alex expires in 24 hours.", actionLabel: "Renew offer", urgency: "high" },
};