import type { Meta, StoryObj } from "@storybook/nextjs";
import { CopilotMessage } from "./copilot-message";

const meta: Meta<typeof CopilotMessage> = { title: "Mothership/CopilotMessage", component: CopilotMessage, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CopilotMessage>;

export const User: Story = { args: { role: "user", content: "Show me 5 senior designers." } };
export const Assistant: Story = { args: { role: "assistant", content: "Here are 5 senior designers ranked by score." } };