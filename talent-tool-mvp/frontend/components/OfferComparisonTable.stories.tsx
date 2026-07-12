import type { Meta, StoryObj } from "@storybook/nextjs";
import OfferComparisonTable from "./OfferComparisonTable";

const meta: Meta<typeof OfferComparisonTable> = { title: "Components/OfferComparisonTable", component: OfferComparisonTable, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof OfferComparisonTable>;

export const Default: Story = {
  args: {
    offers: [
      { id: "1", company: "Acme", base: 120000, bonus: 20000, equity: 50000 },
      { id: "2", company: "Globex", base: 130000, bonus: 15000, equity: 80000 },
    ],
  },
};
export const Single: Story = { args: { offers: [{ id: "1", company: "Acme", base: 100000, bonus: 10000, equity: 30000 }] } };