import type { Meta, StoryObj } from "@storybook/nextjs";
import OfflineBanner from "./OfflineBanner";

const meta: Meta<typeof OfflineBanner> = { title: "Components/OfflineBanner", component: OfflineBanner, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof OfflineBanner>;

export const Online: Story = { args: { online: true } };
export const Offline: Story = { args: { online: false } };