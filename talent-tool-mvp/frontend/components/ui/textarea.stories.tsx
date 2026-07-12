import type { Meta, StoryObj } from "@storybook/nextjs";
import Textarea from "./textarea";

const meta: Meta<typeof Textarea> = {
  title: "UI/Textarea",
  component: Textarea,
  tags: ["autodocs"],
  argTypes: { placeholder: { control: "text" }, rows: { control: "number" } },
};
export default meta;

type Story = StoryObj<typeof Textarea>;

export const Empty: Story = { args: { placeholder: "Add notes...", rows: 4 } };
export const Filled: Story = { args: { defaultValue: "Strong product sense and design systems experience.", rows: 4 } };
export const Disabled: Story = { args: { placeholder: "Locked", disabled: true } };