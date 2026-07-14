import type { Meta, StoryObj } from "@storybook/nextjs";
import { ContactForm } from "./ContactForm";

const meta: Meta<typeof ContactForm> = {
  title: "Forms/ContactForm",
  component: ContactForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof ContactForm>;

export const Default: Story = {
  args: {
    onSubmit: async (v) => console.log(v),
  },
};

export const Prefilled: Story = {
  args: {
    onSubmit: async (v) => console.log(v),
    defaultValues: {
      name: "Ada Lovelace",
      email: "ada@example.com",
      subject: "Enterprise plan question",
      message: "We are hiring 200 engineers this quarter...",
    },
  },
};
