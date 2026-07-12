import type { Meta, StoryObj } from "@storybook/nextjs";
import { NotificationToast } from "./notification-toast";

const meta: Meta<typeof NotificationToast> = { title: "Shared/NotificationToast", component: NotificationToast, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof NotificationToast>;

export const Success: Story = { args: { variant: "success", message: "Candidate saved" } };
export const Error: Story = { args: { variant: "error", message: "Failed to upload CV" } };
export const Info: Story = { args: { variant: "info", message: "New match available" } };