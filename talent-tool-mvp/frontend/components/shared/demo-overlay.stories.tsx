import type { Meta, StoryObj } from "@storybook/nextjs";
import { DemoOverlay } from "./demo-overlay";

const meta: Meta<typeof DemoOverlay> = { title: "Shared/DemoOverlay", component: DemoOverlay, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof DemoOverlay>;

export const Default: Story = { args: { message: "Demo mode — data is mocked" } };
export const Hidden: Story = { args: { message: "Demo mode", visible: false } };