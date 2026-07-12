import type { Meta, StoryObj } from "@storybook/nextjs";
import Skeleton from "./skeleton";

const meta: Meta<typeof Skeleton> = {
  title: "UI/Skeleton",
  component: Skeleton,
  tags: ["autodocs"],
  argTypes: { width: { control: "text" }, height: { control: "text" } },
};
export default meta;
type Story = StoryObj<typeof Skeleton>;

export const Line: Story = { args: { width: "200px", height: "16px" } };
export const Card: Story = { args: { width: "320px", height: "120px" } };
export const Circle: Story = { args: { width: "48px", height: "48px", className: "rounded-full" } };