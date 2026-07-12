import type { Meta, StoryObj } from "@storybook/nextjs";
import { CollectionDetail } from "./collection-detail";

const meta: Meta<typeof CollectionDetail> = { title: "Mothership/CollectionDetail", component: CollectionDetail, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CollectionDetail>;

export const Default: Story = { args: { name: "Q1 Frontend", candidates: [{ id: "1", name: "Sarah Lee" }, { id: "2", name: "John Park" }] } };