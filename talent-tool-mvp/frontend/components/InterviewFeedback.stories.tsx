import type { Meta, StoryObj } from "@storybook/nextjs";
import InterviewFeedback from "./InterviewFeedback";

const meta: Meta<typeof InterviewFeedback> = { title: "Components/InterviewFeedback", component: InterviewFeedback, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof InterviewFeedback>;

export const Default: Story = { args: { candidate: "Sarah Lee", rating: 4, notes: "Strong product sense." } };
export const Negative: Story = { args: { candidate: "John Park", rating: 2, notes: "Limited relevant experience." } };