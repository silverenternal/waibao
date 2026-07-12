import type { Meta, StoryObj } from "@storybook/nextjs";
import ContradictionBadge from "./ContradictionBadge";

const meta: Meta<typeof ContradictionBadge> = { title: "Components/ContradictionBadge", component: ContradictionBadge, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ContradictionBadge>;

export const Default: Story = { args: { count: 2 } };
export const Zero: Story = { args: { count: 0 } };