import type { Meta, StoryObj } from "@storybook/nextjs";
import JournalAdviceList from "./JournalAdviceList";

const meta: Meta<typeof JournalAdviceList> = { title: "Components/JournalAdviceList", component: JournalAdviceList, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof JournalAdviceList>;

export const Default: Story = { args: { items: [{ id: "1", text: "Practice the STAR format" }, { id: "2", text: "Review the JD before applying" }] } };
export const Empty: Story = { args: { items: [] } };