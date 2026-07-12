import type { Meta, StoryObj } from "@storybook/nextjs";
import { HandoffRespondDialog } from "./handoff-respond-dialog";

const meta: Meta<typeof HandoffRespondDialog> = { title: "Mothership/HandoffRespondDialog", component: HandoffRespondDialog, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof HandoffRespondDialog>;

export const Default: Story = { args: { open: true, candidate: "Sarah Lee" } };