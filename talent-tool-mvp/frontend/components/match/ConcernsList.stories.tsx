import type { Meta, StoryObj } from "@storybook/nextjs";
import { ConcernsList } from "./ConcernsList";

const meta: Meta<typeof ConcernsList> = { title: "Match/ConcernsList", component: ConcernsList, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ConcernsList>;

export const Default: Story = {
  args: { concerns: ["Limited backend experience", "No team management track record"] },
};
export const Empty: Story = { args: { concerns: [] } };