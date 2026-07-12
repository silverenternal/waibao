import type { Meta, StoryObj } from "@storybook/nextjs";
import { DedupComparison } from "./dedup-comparison";

const meta: Meta<typeof DedupComparison> = { title: "Mothership/DedupComparison", component: DedupComparison, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof DedupComparison>;

export const Default: Story = { args: { leftName: "Sarah Lee", rightName: "Sara Lee", similarity: 0.92 } };
export const Different: Story = { args: { leftName: "Sarah Lee", rightName: "John Park", similarity: 0.15 } };