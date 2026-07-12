import type { Meta, StoryObj } from "@storybook/nextjs";
import ScheduleVideoInterview from "./ScheduleVideoInterview";

const meta: Meta<typeof ScheduleVideoInterview> = { title: "Components/ScheduleVideoInterview", component: ScheduleVideoInterview, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ScheduleVideoInterview>;

export const Default: Story = { args: { candidate: "Sarah Lee", role: "Senior Designer" } };
export const Scheduled: Story = { args: { candidate: "John Park", role: "Engineer", scheduledAt: "2026-02-01T10:00" } };