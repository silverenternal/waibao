import type { Meta, StoryObj } from "@storybook/nextjs";
import { CandidateFilterBar } from "./candidate-filter-bar";

const meta: Meta<typeof CandidateFilterBar> = { title: "Mind/CandidateFilterBar", component: CandidateFilterBar, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CandidateFilterBar>;

export const Default: Story = { args: { skills: ["React", "Python"], locations: ["London"], minScore: 70 } };
export const Empty: Story = { args: {} };