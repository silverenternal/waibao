import type { Meta, StoryObj } from "@storybook/nextjs";
import { CopilotInput } from "./copilot-input";

const meta: Meta<typeof CopilotInput> = { title: "Mothership/CopilotInput", component: CopilotInput, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CopilotInput>;

export const Default: Story = { args: { placeholder: "Ask the copilot..." } };
export const Filled: Story = { args: { placeholder: "Ask...", defaultValue: "Show me top candidates for Senior Designer" } };