import type { Meta, StoryObj } from "@storybook/nextjs";
import { NewsletterSignup } from "./NewsletterSignup";

const meta: Meta<typeof NewsletterSignup> = {
  title: "Forms/NewsletterSignup",
  component: NewsletterSignup,
  tags: ["autodocs"],
};
export default meta;
type Story = StoryObj<typeof NewsletterSignup>;

export const Default: Story = { args: { onSubmit: async (email) => console.log(email) } };
