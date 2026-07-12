import type { Meta, StoryObj } from "@storybook/nextjs";
import EmotionWeekSummary from "./EmotionWeekSummary";

const meta: Meta<typeof EmotionWeekSummary> = { title: "Components/EmotionWeekSummary", component: EmotionWeekSummary, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EmotionWeekSummary>;

export const Default: Story = { args: { week: "2026-W01", summary: { happy: 4, neutral: 2, anxious: 1 } } };