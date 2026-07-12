import type { Meta, StoryObj } from "@storybook/nextjs";
import { SourceBadge } from "./source-badge";

const meta: Meta<typeof SourceBadge> = { title: "Mothership/SourceBadge", component: SourceBadge, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SourceBadge>;

export const LinkedIn: Story = { args: { source: "linkedin" } };
export const Referral: Story = { args: { source: "referral" } };
export const Inbound: Story = { args: { source: "inbound" } };