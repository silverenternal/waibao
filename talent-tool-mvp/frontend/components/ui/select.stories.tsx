import type { Meta, StoryObj } from "@storybook/nextjs";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "./select";

const meta: Meta<typeof Select> = { title: "UI/Select", component: Select, tags: ["autodocs"] };
export default meta;

type Story = StoryObj<typeof Select>;

export const Default: Story = {
  render: () => (
    <Select>
      <SelectTrigger className="w-[200px]">
        <SelectValue placeholder="Choose status" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="active">Active</SelectItem>
        <SelectItem value="paused">Paused</SelectItem>
        <SelectItem value="archived">Archived</SelectItem>
      </SelectContent>
    </Select>
  ),
};