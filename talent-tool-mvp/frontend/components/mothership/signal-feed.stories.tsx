import type { Meta, StoryObj } from "@storybook/nextjs";
import { SignalFeed } from "./signal-feed";

const meta: Meta<typeof SignalFeed> = { title: "Mothership/SignalFeed", component: SignalFeed, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SignalFeed>;

export const Default: Story = { args: { signals: [{ id: "1", type: "view", label: "Sarah viewed Senior Designer" }, { id: "2", type: "apply", label: "John applied to Engineer" }] } };
export const Empty: Story = { args: { signals: [] } };