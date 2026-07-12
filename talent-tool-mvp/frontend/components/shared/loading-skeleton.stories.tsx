import type { Meta, StoryObj } from "@storybook/nextjs";
import { LoadingSkeleton } from "./loading-skeleton";

const meta: Meta<typeof LoadingSkeleton> = { title: "Shared/LoadingSkeleton", component: LoadingSkeleton, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof LoadingSkeleton>;

export const Card: Story = { args: { variant: "card" } };
export const List: Story = { args: { variant: "list", count: 3 } };
export const Table: Story = { args: { variant: "table", count: 5 } };