import type { Meta, StoryObj } from "@storybook/nextjs";
import { ApiKeyForm } from "./ApiKeyForm";

const meta: Meta<typeof ApiKeyForm> = {
  title: "Forms/ApiKeyForm",
  component: ApiKeyForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof ApiKeyForm>;

const scopes = [
  { value: "read", label: "Read" },
  { value: "write", label: "Write" },
  { value: "admin", label: "Admin" },
];

export const Default: Story = { args: { onSubmit: async (v) => console.log(v), scopeOptions: scopes } };
