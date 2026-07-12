import type { Meta, StoryObj } from "@storybook/nextjs";
import InstallPrompt from "./InstallPrompt";

const meta: Meta<typeof InstallPrompt> = { title: "Components/InstallPrompt", component: InstallPrompt, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof InstallPrompt>;

export const Default: Story = { args: {} };
export const iOS: Story = { args: { platform: "ios" } };