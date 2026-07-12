import type { Meta, StoryObj } from "@storybook/nextjs";
import NeedsList from "./NeedsList";

const meta: Meta<typeof NeedsList> = { title: "Components/NeedsList", component: NeedsList, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof NeedsList>;

export const Default: Story = { args: { items: ["More senior ICs", "Strong backend"] } };
export const Empty: Story = { args: { items: [] } };