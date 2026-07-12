import type { Meta, StoryObj } from "@storybook/nextjs";
import CalendarSync from "./CalendarSync";

const meta: Meta<typeof CalendarSync> = { title: "Components/CalendarSync", component: CalendarSync, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CalendarSync>;

export const Default: Story = { args: { provider: "google" } };
export const Outlook: Story = { args: { provider: "outlook" } };