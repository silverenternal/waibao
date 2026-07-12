import type { Meta, StoryObj } from "@storybook/nextjs";
import VoiceRecorder from "./VoiceRecorder";

const meta: Meta<typeof VoiceRecorder> = { title: "Components/VoiceRecorder", component: VoiceRecorder, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof VoiceRecorder>;

export const Idle: Story = { args: { state: "idle" } };
export const Recording: Story = { args: { state: "recording" } };