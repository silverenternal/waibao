import type { Meta, StoryObj } from "@storybook/nextjs";
import Checkbox from "./checkbox";

const meta: Meta<typeof Checkbox> = {
  title: "UI/Checkbox",
  component: Checkbox,
  tags: ["autodocs"],
  argTypes: { disabled: { control: "boolean" }, checked: { control: "boolean" } },
};
export default meta;

type Story = StoryObj<typeof Checkbox>;

export const Unchecked: Story = { args: { label: "Accept terms" } };
export const Checked: Story = { args: { label: "Subscribe", defaultChecked: true } };
export const Disabled: Story = { args: { label: "Disabled", disabled: true } };