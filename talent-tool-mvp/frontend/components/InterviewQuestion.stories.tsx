import type { Meta, StoryObj } from "@storybook/nextjs";
import InterviewQuestion from "./InterviewQuestion";

const meta: Meta<typeof InterviewQuestion> = { title: "Components/InterviewQuestion", component: InterviewQuestion, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof InterviewQuestion>;

export const Default: Story = { args: { question: "Tell me about your design process." } };
export const WithAnswer: Story = { args: { question: "Why this role?", answer: "Looking for design systems scale." } };