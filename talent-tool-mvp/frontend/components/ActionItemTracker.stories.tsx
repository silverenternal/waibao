import type { Meta, StoryObj } from "@storybook/nextjs";
import ActionItemTracker from "./ActionItemTracker";

const meta: Meta<typeof ActionItemTracker> = { title: "Components/ActionItemTracker", component: ActionItemTracker, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ActionItemTracker>;

export const Default: Story = { args: { items: [{ id: "1", label: "Schedule interview", done: false }, { id: "2", label: "Send offer", done: true }] } };
export const Empty: Story = { args: { items: [] } };