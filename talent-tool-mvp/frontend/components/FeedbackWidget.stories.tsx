import type { Meta, StoryObj } from "@storybook/nextjs";
import FeedbackWidget from "./FeedbackWidget";

const meta: Meta<typeof FeedbackWidget> = { title: "Components/FeedbackWidget", component: FeedbackWidget, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof FeedbackWidget>;

export const Default: Story = { args: {} };
export const Submitted: Story = { args: { submitted: true } };