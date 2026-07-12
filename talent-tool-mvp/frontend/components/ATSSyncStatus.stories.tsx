import type { Meta, StoryObj } from "@storybook/nextjs";
import ATSSyncStatus from "./ATSSyncStatus";

const meta: Meta<typeof ATSSyncStatus> = { title: "Components/ATSSyncStatus", component: ATSSyncStatus, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ATSSyncStatus>;

export const Syncing: Story = { args: { state: "syncing" } };
export const Idle: Story = { args: { state: "idle" } };
export const Error: Story = { args: { state: "error" } };