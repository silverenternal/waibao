import type { Meta, StoryObj } from "@storybook/nextjs";
import ReasoningTrace from "./ReasoningTrace";

const meta: Meta<typeof ReasoningTrace> = { title: "Components/ReasoningTrace", component: ReasoningTrace, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ReasoningTrace>;

export const Default: Story = { args: { steps: ["Parsed CV", "Extracted skills", "Computed match score"] } };
export const Single: Story = { args: { steps: ["Computed match score"] } };