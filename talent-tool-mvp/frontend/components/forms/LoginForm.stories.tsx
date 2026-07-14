import type { Meta, StoryObj } from "@storybook/nextjs";
import { LoginForm } from "./LoginForm";

const meta: Meta<typeof LoginForm> = {
  title: "Forms/LoginForm",
  component: LoginForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof LoginForm>;

export const Default: Story = { args: { onSubmit: async (v) => console.log(v) } };
export const WithRememberedEmail: Story = {
  args: { onSubmit: async (v) => console.log(v), defaultEmail: "returning@example.com" },
};
