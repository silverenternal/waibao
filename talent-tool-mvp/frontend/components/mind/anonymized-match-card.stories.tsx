import type { Meta, StoryObj } from "@storybook/nextjs";
import { AnonymizedMatchCard } from "./anonymized-match-card";

const meta: Meta<typeof AnonymizedMatchCard> = { title: "Mind/AnonymizedMatchCard", component: AnonymizedMatchCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof AnonymizedMatchCard>;

export const Default: Story = {
  args: { anonymousId: "CAND-001", score: 88, skills: ["React", "TypeScript"], location: "London" },
};
export const Partial: Story = {
  args: { anonymousId: "CAND-002", score: 64, skills: ["Python"] },
};