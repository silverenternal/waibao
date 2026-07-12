import type { Meta, StoryObj } from "@storybook/nextjs";
import { HandoffStatusBadge } from "./handoff-status-badge";

const meta: Meta<typeof HandoffStatusBadge> = { title: "Mothership/HandoffStatusBadge", component: HandoffStatusBadge, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof HandoffStatusBadge>;

export const Pending: Story = { args: { status: "pending" } };
export const Accepted: Story = { args: { status: "accepted" } };
export const Declined: Story = { args: { status: "declined" } };