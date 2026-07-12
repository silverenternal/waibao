import type { Meta, StoryObj } from "@storybook/nextjs";
import { QuoteCard } from "./quote-card";

const meta: Meta<typeof QuoteCard> = { title: "Mind/QuoteCard", component: QuoteCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof QuoteCard>;

export const Default: Story = { args: { amount: 4500, currency: "GBP", role: "Senior Designer" } };
export const Accepted: Story = { args: { amount: 6000, currency: "USD", role: "Eng Manager", status: "accepted" } };