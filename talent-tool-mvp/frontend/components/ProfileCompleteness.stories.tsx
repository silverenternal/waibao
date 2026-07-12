import type { Meta, StoryObj } from "@storybook/nextjs";
import ProfileCompleteness from "./ProfileCompleteness";

const meta: Meta<typeof ProfileCompleteness> = { title: "Components/ProfileCompleteness", component: ProfileCompleteness, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ProfileCompleteness>;

export const Low: Story = { args: { percent: 35 } };
export const Medium: Story = { args: { percent: 65 } };
export const High: Story = { args: { percent: 92 } };