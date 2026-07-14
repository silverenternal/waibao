import type { Meta, StoryObj } from "@storybook/nextjs";
import { SignupForm } from "./SignupForm";

const meta: Meta<typeof SignupForm> = {
  title: "Forms/SignupForm",
  component: SignupForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof SignupForm>;

export const Default: Story = { args: { onSubmit: async (v) => console.log(v) } };
