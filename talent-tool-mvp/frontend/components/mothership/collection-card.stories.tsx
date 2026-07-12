import type { Meta, StoryObj } from "@storybook/nextjs";
import { CollectionCard } from "./collection-card";

const meta: Meta<typeof CollectionCard> = { title: "Mothership/CollectionCard", component: CollectionCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CollectionCard>;

export const Default: Story = { args: { name: "Q1 Frontend pipeline", count: 24 } };
export const Large: Story = { args: { name: "Senior ICs", count: 87 } };