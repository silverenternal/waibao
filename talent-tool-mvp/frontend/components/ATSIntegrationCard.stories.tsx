import type { Meta, StoryObj } from "@storybook/nextjs";
import ATSIntegrationCard from "./ATSIntegrationCard";

const meta: Meta<typeof ATSIntegrationCard> = { title: "Components/ATSIntegrationCard", component: ATSIntegrationCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ATSIntegrationCard>;

export const Default: Story = { args: { name: "Bullhorn", status: "connected", lastSync: "2026-01-01" } };
export const Disconnected: Story = { args: { name: "Greenhouse", status: "disconnected" } };