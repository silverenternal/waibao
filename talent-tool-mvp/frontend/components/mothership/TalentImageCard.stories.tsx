import type { Meta, StoryObj } from "@storybook/nextjs";
import { TalentImageCard } from "./TalentImageCard";

const meta: Meta<typeof TalentImageCard> = { title: "Mothership/TalentImageCard", component: TalentImageCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof TalentImageCard>;

export const Default: Story = { args: { name: "Sarah Lee", role: "Designer", imageUrl: "https://github.com/shadcn.png" } };
export const NoImage: Story = { args: { name: "John Park", role: "Engineer" } };