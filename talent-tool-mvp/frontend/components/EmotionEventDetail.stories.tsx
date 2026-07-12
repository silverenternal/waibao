import type { Meta, StoryObj } from "@storybook/nextjs";
import EmotionEventDetail from "./EmotionEventDetail";

const meta: Meta<typeof EmotionEventDetail> = { title: "Components/EmotionEventDetail", component: EmotionEventDetail, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EmotionEventDetail>;

export const Default: Story = { args: { event: { emotion: "happy", trigger: "Interview offer", at: "2026-01-01" } } };