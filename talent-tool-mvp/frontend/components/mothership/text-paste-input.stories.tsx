import type { Meta, StoryObj } from "@storybook/nextjs";
import { TextPasteInput } from "./text-paste-input";

const meta: Meta<typeof TextPasteInput> = { title: "Mothership/TextPasteInput", component: TextPasteInput, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof TextPasteInput>;

export const Default: Story = { args: { placeholder: "Paste CV text..." } };
export const Filled: Story = { args: { placeholder: "Paste...", defaultValue: "Senior designer with 8 years..." } };