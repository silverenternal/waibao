import type { Meta, StoryObj } from "@storybook/nextjs";
import { CollectionForm } from "./collection-form";

const meta: Meta<typeof CollectionForm> = { title: "Mothership/CollectionForm", component: CollectionForm, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CollectionForm>;

export const Default: Story = { args: {} };