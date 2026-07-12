import type { Meta, StoryObj } from "@storybook/nextjs";
import { EvalDiscuss } from "./EvalDiscuss";

const meta: Meta<typeof EvalDiscuss> = { title: "Match/EvalDiscuss", component: EvalDiscuss, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EvalDiscuss>;

export const Default: Story = { args: { prompt: "Why does the employer score this candidate lower than the candidate's self-evaluation?" } };
export const Filled: Story = { args: { prompt: "Question", response: "Employer weighted Kubernetes heavily; candidate lacks K8s." } };