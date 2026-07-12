import type { Meta, StoryObj } from "@storybook/nextjs";
import { HandoffCard } from "./handoff-card";

const meta: Meta<typeof HandoffCard> = { title: "Mothership/HandoffCard", component: HandoffCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof HandoffCard>;

export const Default: Story = { args: { candidate: "Sarah Lee", role: "Senior Designer", status: "pending" } };
export const Accepted: Story = { args: { candidate: "John Park", role: "Engineer", status: "accepted" } };