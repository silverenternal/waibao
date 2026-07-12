import type { Meta, StoryObj } from "@storybook/nextjs";
import JournalWarningTimeline from "./JournalWarningTimeline";

const meta: Meta<typeof JournalWarningTimeline> = { title: "Components/JournalWarningTimeline", component: JournalWarningTimeline, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof JournalWarningTimeline>;

export const Default: Story = { args: { events: [{ at: "2026-01-01", label: "Burst of anxiety" }, { at: "2026-01-05", label: "Recovery" }] } };