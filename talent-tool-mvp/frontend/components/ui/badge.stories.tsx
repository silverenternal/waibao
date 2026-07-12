import type { Meta, StoryObj } from "@storybook/nextjs";
import Badge from "./badge";

const meta: Meta<typeof Badge> = {
  title: "UI/Badge",
  component: Badge,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: { type: "select" },
      options: ["default", "secondary", "destructive", "outline"],
    },
  },
};
export default meta;

type Story = StoryObj<typeof Badge>;

export const Default: Story = { args: { children: "Active" } };
export const Secondary: Story = { args: { children: "Archived", variant: "secondary" } };
export const Destructive: Story = { args: { children: "Rejected", variant: "destructive" } };
export const Outline: Story = { args: { children: "Pending", variant: "outline" } };