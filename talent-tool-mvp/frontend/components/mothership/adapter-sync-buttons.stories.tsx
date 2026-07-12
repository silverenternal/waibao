import type { Meta, StoryObj } from "@storybook/nextjs";
import { AdapterSyncButtons } from "./adapter-sync-buttons";

const meta: Meta<typeof AdapterSyncButtons> = { title: "Mothership/AdapterSyncButtons", component: AdapterSyncButtons, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof AdapterSyncButtons>;

export const Default: Story = { args: { adapters: ["bullhorn", "hubspot"] } };
export const Single: Story = { args: { adapters: ["linkedin"] } };