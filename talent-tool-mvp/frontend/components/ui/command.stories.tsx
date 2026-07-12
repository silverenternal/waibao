import type { Meta, StoryObj } from "@storybook/nextjs";
import { Command, CommandInput, CommandList, CommandItem, CommandEmpty } from "./command";

const meta: Meta<typeof Command> = { title: "UI/Command", component: Command, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Command>;

export const Default: Story = {
  render: () => (
    <Command className="w-[320px] border">
      <CommandInput placeholder="Type a command..." />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandItem>Calendar</CommandItem>
        <CommandItem>Search</CommandItem>
        <CommandItem>Settings</CommandItem>
      </CommandList>
    </Command>
  ),
};