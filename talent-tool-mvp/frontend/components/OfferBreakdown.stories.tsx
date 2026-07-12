import type { Meta, StoryObj } from "@storybook/nextjs";
import OfferBreakdown from "./OfferBreakdown";

const meta: Meta<typeof OfferBreakdown> = { title: "Components/OfferBreakdown", component: OfferBreakdown, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof OfferBreakdown>;

export const Default: Story = { args: { base: 120000, bonus: 20000, equity: 50000 } };
export const HighEquity: Story = { args: { base: 100000, bonus: 15000, equity: 200000 } };