import type { Meta, StoryObj } from "@storybook/nextjs";
import { CandidateCard } from "./candidate-card";

const meta: Meta<typeof CandidateCard> = {
  title: "Shared/CandidateCard",
  component: CandidateCard,
  tags: ["autodocs"],
};
export default meta;
type Story = StoryObj<typeof CandidateCard>;

export const Default: Story = {
  args: {
    name: "Sarah Lee",
    headline: "Senior Product Designer",
    score: 92,
    skills: ["Figma", "Design Systems", "User Research"],
    location: "London, UK",
  },
};

export const LowScore: Story = {
  args: {
    name: "John Park",
    headline: "Junior Engineer",
    score: 58,
    skills: ["Python", "Flask"],
    location: "Remote",
  },
};