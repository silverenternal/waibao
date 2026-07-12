import type { Meta, StoryObj } from "@storybook/nextjs";
import Button from "./button";

const meta: Meta<typeof Button> = {
  title: "UI/Button",
  component: Button,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: { type: "select" },
      options: ["default", "outline", "secondary", "ghost", "destructive", "link"],
    },
    size: {
      control: { type: "select" },
      options: ["default", "xs", "sm", "lg", "icon"],
    },
    disabled: { control: "boolean" },
  },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = { args: { children: "Save candidate", variant: "default" } };
export const Outline: Story = { args: { children: "Cancel", variant: "outline" } };
export const Destructive: Story = { args: { children: "Reject", variant: "destructive" } };
export const Ghost: Story = { args: { children: "Skip", variant: "ghost" } };
export const Link: Story = { args: { children: "Learn more", variant: "link" } };
export const Small: Story = { args: { children: "Compact", size: "sm" } };
export const Large: Story = { args: { children: "Large", size: "lg" } };
export const Disabled: Story = { args: { children: "Disabled", disabled: true } };