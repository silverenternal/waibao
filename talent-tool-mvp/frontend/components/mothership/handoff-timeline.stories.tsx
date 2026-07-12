import type { Meta, StoryObj } from "@storybook/nextjs";
import { HandoffTimeline } from "./handoff-timeline";

const meta: Meta<typeof HandoffTimeline> = { title: "Mothership/HandoffTimeline", component: HandoffTimeline, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof HandoffTimeline>;

export const Default: Story = {
  args: { events: [{ at: "2026-01-01", label: "Created" }, { at: "2026-01-02", label: "Sent" }, { at: "2026-01-03", label: "Accepted" }] },
};