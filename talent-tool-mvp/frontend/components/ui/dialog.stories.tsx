import type { Meta, StoryObj } from "@storybook/nextjs";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./dialog";

const meta: Meta<typeof Dialog> = { title: "UI/Dialog", component: Dialog, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Dialog>;

export const Basic: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger>Open</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm action</DialogTitle>
          <DialogDescription>Are you sure you want to continue?</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <button>Cancel</button>
          <button>Continue</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};