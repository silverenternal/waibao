import type { Meta, StoryObj } from "@storybook/nextjs";
import { CandidateGrid } from "./candidate-grid";

const meta: Meta<typeof CandidateGrid> = { title: "Mind/CandidateGrid", component: CandidateGrid, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CandidateGrid>;

export const Default: Story = {
  args: {
    candidates: [
      { id: "1", name: "Sarah Lee", score: 92 },
      { id: "2", name: "John Park", score: 71 },
      { id: "3", name: "Anna Sun", score: 84 },
    ],
  },
};