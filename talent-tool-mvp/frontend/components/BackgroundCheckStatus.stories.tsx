import type { Meta, StoryObj } from "@storybook/nextjs";
import BackgroundCheckStatus from "./BackgroundCheckStatus";

const meta: Meta<typeof BackgroundCheckStatus> = { title: "Components/BackgroundCheckStatus", component: BackgroundCheckStatus, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof BackgroundCheckStatus>;

export const Clear: Story = { args: { status: "clear", candidate: "Sarah Lee" } };
export const Pending: Story = { args: { status: "pending", candidate: "John Park" } };