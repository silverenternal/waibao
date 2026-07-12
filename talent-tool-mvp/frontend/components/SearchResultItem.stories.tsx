import type { Meta, StoryObj } from "@storybook/nextjs";
import SearchResultItem from "./SearchResultItem";

const meta: Meta<typeof SearchResultItem> = { title: "Components/SearchResultItem", component: SearchResultItem, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SearchResultItem>;

export const Candidate: Story = { args: { type: "candidate", title: "Sarah Lee", subtitle: "Senior Designer" } };
export const Role: Story = { args: { type: "role", title: "Senior Designer", subtitle: "Acme Talent" } };