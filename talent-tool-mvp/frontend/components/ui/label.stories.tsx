import type { Meta, StoryObj } from "@storybook/nextjs";
import Label from "./label";

const meta: Meta<typeof Label> = { title: "UI/Label", component: Label, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Label>;

export const Default: Story = { args: { children: "Email address" } };
export const Required: Story = { args: { children: "Full name *", htmlFor: "name" } };