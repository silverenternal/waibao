import type { Meta, StoryObj } from "@storybook/nextjs";
import ProfileCard from "./ProfileCard";

const meta: Meta<typeof ProfileCard> = { title: "Components/ProfileCard", component: ProfileCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ProfileCard>;

export const Default: Story = { args: { name: "Sarah Lee", title: "Senior Designer", location: "London" } };
export const Remote: Story = { args: { name: "John Park", title: "Engineer", location: "Remote" } };