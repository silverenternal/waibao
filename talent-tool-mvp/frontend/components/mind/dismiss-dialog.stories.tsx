import type { Meta, StoryObj } from "@storybook/nextjs";
import { DismissDialog } from "./dismiss-dialog";

const meta: Meta<typeof DismissDialog> = { title: "Mind/DismissDialog", component: DismissDialog, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof DismissDialog>;

export const Default: Story = { args: { candidateName: "Sarah Lee", reason: "Not a fit for current roles" } };