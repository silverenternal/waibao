import type { Meta, StoryObj } from "@storybook/nextjs";
import { StrengthsList } from "./StrengthsList";

const meta: Meta<typeof StrengthsList> = { title: "Match/StrengthsList", component: StrengthsList, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof StrengthsList>;

export const Default: Story = {
  args: { strengths: ["8 yrs design systems", "Led 3 product launches", "Cross-functional leadership"] },
};
export const Empty: Story = { args: { strengths: [] } };