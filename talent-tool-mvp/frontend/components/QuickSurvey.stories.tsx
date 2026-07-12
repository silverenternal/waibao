import type { Meta, StoryObj } from "@storybook/nextjs";
import QuickSurvey from "./QuickSurvey";

const meta: Meta<typeof QuickSurvey> = { title: "Components/QuickSurvey", component: QuickSurvey, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof QuickSurvey>;

export const Default: Story = { args: { question: "How was your experience?", options: ["Great", "OK", "Bad"] } };