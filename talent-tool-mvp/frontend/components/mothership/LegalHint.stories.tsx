import type { Meta, StoryObj } from "@storybook/nextjs";
import { LegalHint } from "./LegalHint";

const meta: Meta<typeof LegalHint> = { title: "Mothership/LegalHint", component: LegalHint, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof LegalHint>;

export const Default: Story = { args: { message: "Make sure to anonymise candidate names before sharing externally." } };