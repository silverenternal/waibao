import type { Meta, StoryObj } from "@storybook/nextjs";
import { MatchDetailCard } from "./match-detail-card";

const meta: Meta<typeof MatchDetailCard> = { title: "Mothership/MatchDetailCard", component: MatchDetailCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof MatchDetailCard>;

export const Default: Story = { args: { candidate: "Sarah Lee", role: "Senior Designer", score: 91, reasons: ["Strong portfolio"] } };