import type { Meta, StoryObj } from "@storybook/nextjs";
import GlobalSearchPalette from "./GlobalSearchPalette";

const meta: Meta<typeof GlobalSearchPalette> = { title: "Components/GlobalSearchPalette", component: GlobalSearchPalette, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof GlobalSearchPalette>;

export const Default: Story = { args: { open: true } };
export const WithResults: Story = { args: { open: true, results: [{ id: "1", title: "Sarah Lee" }, { id: "2", title: "Senior Designer role" }] } };