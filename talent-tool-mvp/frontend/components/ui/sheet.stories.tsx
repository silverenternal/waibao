import type { Meta, StoryObj } from "@storybook/nextjs";
import { Sheet, SheetTrigger, SheetContent, SheetHeader, SheetTitle } from "./sheet";

const meta: Meta<typeof Sheet> = { title: "UI/Sheet", component: Sheet, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Sheet>;

export const Right: Story = {
  render: () => (
    <Sheet>
      <SheetTrigger>Open panel</SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Filters</SheetTitle>
        </SheetHeader>
        <div>Filters content</div>
      </SheetContent>
    </Sheet>
  ),
};