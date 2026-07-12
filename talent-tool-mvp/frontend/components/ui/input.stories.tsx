import type { Meta, StoryObj } from "@storybook/nextjs";
import Input from "./input";

const meta: Meta<typeof Input> = {
  title: "UI/Input",
  component: Input,
  tags: ["autodocs"],
  argTypes: {
    placeholder: { control: "text" },
    disabled: { control: "boolean" },
  },
};
export default meta;

type Story = StoryObj<typeof Input>;

export const Empty: Story = { args: { placeholder: "Search candidates..." } };
export const Filled: Story = { args: { defaultValue: "Sarah Lee" } };
export const Disabled: Story = { args: { placeholder: "Disabled", disabled: true } };
export const Email: Story = { args: { type: "email", placeholder: "you@example.com" } };