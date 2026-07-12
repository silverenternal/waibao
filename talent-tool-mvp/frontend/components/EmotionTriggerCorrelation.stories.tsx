import type { Meta, StoryObj } from "@storybook/nextjs";
import EmotionTriggerCorrelation from "./EmotionTriggerCorrelation";

const meta: Meta<typeof EmotionTriggerCorrelation> = { title: "Components/EmotionTriggerCorrelation", component: EmotionTriggerCorrelation, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EmotionTriggerCorrelation>;

export const Default: Story = { args: { trigger: "Offer received", correlation: 0.83 } };
export const Negative: Story = { args: { trigger: "Rejection", correlation: -0.6 } };