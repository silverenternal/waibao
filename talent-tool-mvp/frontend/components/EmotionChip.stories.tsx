import type { Meta, StoryObj } from "@storybook/nextjs";
import EmotionChip from "./EmotionChip";

const meta: Meta<typeof EmotionChip> = { title: "Components/EmotionChip", component: EmotionChip, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EmotionChip>;

export const Happy: Story = { args: { emotion: "happy", score: 0.9 } };
export const Neutral: Story = { args: { emotion: "neutral", score: 0.5 } };
export const Anxious: Story = { args: { emotion: "anxious", score: 0.7 } };