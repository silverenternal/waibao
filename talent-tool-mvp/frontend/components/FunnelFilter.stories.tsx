import type { Meta, StoryObj } from "@storybook/nextjs";
import FunnelFilter from "./FunnelFilter";

const meta: Meta<typeof FunnelFilter> = { title: "Components/FunnelFilter", component: FunnelFilter, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof FunnelFilter>;

export const Default: Story = { args: { stages: ["Applied", "Screened", "Interviewed", "Offered"] } };