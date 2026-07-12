import type { Meta, StoryObj } from "@storybook/nextjs";
import { HandoffSendDialog } from "./handoff-send-dialog";

const meta: Meta<typeof HandoffSendDialog> = { title: "Mothership/HandoffSendDialog", component: HandoffSendDialog, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof HandoffSendDialog>;

export const Default: Story = { args: { open: true, recipient: "Acme Talent" } };