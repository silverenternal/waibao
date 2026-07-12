import type { Meta, StoryObj } from "@storybook/nextjs";
import Progress from "./progress";

const meta: Meta<typeof Progress> = {
  title: "UI/Progress",
  component: Progress,
  tags: ["autodocs"],
  argTypes: { value: { control: { type: "range", min: 0, max: 100, step: 1 } } },
};
export default meta;
type Story = StoryObj<typeof Progress>;

export const Empty: Story = { args: { value: 0 } };
export const Half: Story = { args: { value: 50 } };
export const AlmostFull: Story = { args: { value: 92 } };
export const Complete: Story = { args: { value: 100 } };