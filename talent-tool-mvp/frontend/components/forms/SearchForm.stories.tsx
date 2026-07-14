import type { Meta, StoryObj } from "@storybook/nextjs";
import { SearchForm } from "./SearchForm";

const meta: Meta<typeof SearchForm> = {
  title: "Forms/SearchForm",
  component: SearchForm,
  tags: ["autodocs"],
};
export default meta;
type Story = StoryObj<typeof SearchForm>;

export const Default: Story = { args: { onSubmit: async (v) => console.log(v) } };
