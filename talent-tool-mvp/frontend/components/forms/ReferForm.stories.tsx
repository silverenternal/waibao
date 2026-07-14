import type { Meta, StoryObj } from "@storybook/nextjs";
import { ReferForm } from "./ReferForm";

const meta: Meta<typeof ReferForm> = {
  title: "Forms/ReferForm",
  component: ReferForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof ReferForm>;

export const Default: Story = { args: { onSubmit: async (v) => console.log(v) } };
