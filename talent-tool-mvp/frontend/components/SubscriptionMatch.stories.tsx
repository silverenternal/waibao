import type { Meta, StoryObj } from "@storybook/nextjs";
import SubscriptionMatch from "./SubscriptionMatch";

const meta: Meta<typeof SubscriptionMatch> = { title: "Components/SubscriptionMatch", component: SubscriptionMatch, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SubscriptionMatch>;

export const Default: Story = { args: { role: "Senior Designer", candidates: [{ id: "1", name: "Sarah Lee" }] } };