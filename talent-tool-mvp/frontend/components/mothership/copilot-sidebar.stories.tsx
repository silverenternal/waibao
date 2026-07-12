import type { Meta, StoryObj } from "@storybook/nextjs";
import { CopilotSidebar } from "./copilot-sidebar";

const meta: Meta<typeof CopilotSidebar> = { title: "Mothership/CopilotSidebar", component: CopilotSidebar, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CopilotSidebar>;

export const Default: Story = { args: {} };
export const Open: Story = { args: { open: true } };