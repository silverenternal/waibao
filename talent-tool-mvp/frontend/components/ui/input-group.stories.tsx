import type { Meta, StoryObj } from "@storybook/nextjs";
import { InputGroup, InputGroupInput, InputGroupAddon } from "./input-group";

const meta: Meta<typeof InputGroup> = { title: "UI/InputGroup", component: InputGroup, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof InputGroup>;

export const WithLeading: Story = {
  render: () => (
    <InputGroup>
      <InputGroupAddon align="inline-start">@</InputGroupAddon>
      <InputGroupInput placeholder="username" />
    </InputGroup>
  ),
};

export const WithTrailing: Story = {
  render: () => (
    <InputGroup>
      <InputGroupInput placeholder="Search" />
      <InputGroupAddon align="inline-end">⌘K</InputGroupAddon>
    </InputGroup>
  ),
};