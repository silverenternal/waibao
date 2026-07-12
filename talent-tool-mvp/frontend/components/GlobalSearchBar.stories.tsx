import type { Meta, StoryObj } from "@storybook/nextjs";
import GlobalSearchBar from "./GlobalSearchBar";

const meta: Meta<typeof GlobalSearchBar> = { title: "Components/GlobalSearchBar", component: GlobalSearchBar, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof GlobalSearchBar>;

export const Default: Story = { args: {} };
export const WithQuery: Story = { args: { defaultValue: "Senior Designer" } };