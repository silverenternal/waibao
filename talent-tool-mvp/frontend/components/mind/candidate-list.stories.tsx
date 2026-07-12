import type { Meta, StoryObj } from "@storybook/nextjs";
import { CandidateList } from "./candidate-list";

const meta: Meta<typeof CandidateList> = { title: "Mind/CandidateList", component: CandidateList, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CandidateList>;

export const Default: Story = {
  args: {
    candidates: [
      { id: "1", name: "Sarah Lee", headline: "Senior Designer" },
      { id: "2", name: "John Park", headline: "Engineer" },
    ],
  },
};