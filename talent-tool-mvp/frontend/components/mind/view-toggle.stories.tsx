import type { Meta, StoryObj } from "@storybook/nextjs";
import { ViewToggle } from "./view-toggle";

const meta: Meta<typeof ViewToggle> = { title: "Mind/ViewToggle", component: ViewToggle, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ViewToggle>;

export const Default: Story = { args: { view: "grid" } };
export const List: Story = { args: { view: "list" } };