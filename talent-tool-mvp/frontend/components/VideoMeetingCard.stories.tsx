import type { Meta, StoryObj } from "@storybook/nextjs";
import VideoMeetingCard from "./VideoMeetingCard";

const meta: Meta<typeof VideoMeetingCard> = { title: "Components/VideoMeetingCard", component: VideoMeetingCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof VideoMeetingCard>;

export const Default: Story = { args: { title: "Interview with Sarah", scheduledAt: "2026-02-01T10:00" } };
export const Past: Story = { args: { title: "Past interview", scheduledAt: "2025-12-01T10:00", past: true } };