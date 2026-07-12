import type { Meta, StoryObj } from "@storybook/nextjs";
import { Popover, PopoverTrigger, PopoverContent } from "./popover";

const meta: Meta<typeof Popover> = { title: "UI/Popover", component: Popover, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Popover>;

export const Default: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger>Open popover</PopoverTrigger>
      <PopoverContent>Some content inside popover.</PopoverContent>
    </Popover>
  ),
};