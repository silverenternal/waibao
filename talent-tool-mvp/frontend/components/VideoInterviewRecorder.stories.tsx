import type { Meta, StoryObj } from "@storybook/nextjs";
import VideoInterviewRecorder from "./VideoInterviewRecorder";

const meta: Meta<typeof VideoInterviewRecorder> = { title: "Components/VideoInterviewRecorder", component: VideoInterviewRecorder, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof VideoInterviewRecorder>;

export const Idle: Story = { args: { state: "idle" } };
export const Recording: Story = { args: { state: "recording" } };
export const Stopped: Story = { args: { state: "stopped" } };