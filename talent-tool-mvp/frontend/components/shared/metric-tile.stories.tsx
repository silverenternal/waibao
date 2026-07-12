import type { Meta, StoryObj } from "@storybook/nextjs";
import { MetricTile } from "./metric-tile";

const meta: Meta<typeof MetricTile> = { title: "Shared/MetricTile", component: MetricTile, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof MetricTile>;

export const Default: Story = { args: { label: "Active roles", value: 24, trend: "+3 this week" } };
export const Negative: Story = { args: { label: "Drop-off rate", value: "12%", trend: "-2% MoM" } };
export const Large: Story = { args: { label: "Pipeline value", value: "£1.2M", trend: "+8% QoQ" } };