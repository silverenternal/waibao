import type { Meta, StoryObj } from "@storybook/nextjs";
import { QuoteRequestDialog } from "./quote-request-dialog";

const meta: Meta<typeof QuoteRequestDialog> = { title: "Mind/QuoteRequestDialog", component: QuoteRequestDialog, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof QuoteRequestDialog>;

export const Default: Story = { args: { open: true, roleTitle: "Senior Designer" } };