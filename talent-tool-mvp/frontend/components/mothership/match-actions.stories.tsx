import type { Meta, StoryObj } from "@storybook/nextjs";
import { MatchActions } from "./match-actions";

const meta: Meta<typeof MatchActions> = { title: "Mothership/MatchActions", component: MatchActions, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof MatchActions>;

export const Default: Story = { args: { matchId: "m_123" } };
export const Hired: Story = { args: { matchId: "m_456", status: "hired" } };