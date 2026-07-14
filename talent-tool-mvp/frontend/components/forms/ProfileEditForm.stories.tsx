import type { Meta, StoryObj } from "@storybook/nextjs";
import { ProfileEditForm } from "./ProfileEditForm";

const meta: Meta<typeof ProfileEditForm> = {
  title: "Forms/ProfileEditForm",
  component: ProfileEditForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof ProfileEditForm>;

export const Default: Story = { args: { onSubmit: async (v) => console.log(v) } };
export const Prefilled: Story = {
  args: {
    onSubmit: async (v) => console.log(v),
    defaultValues: {
      name: "Grace Hopper",
      headline: "Computer Scientist",
      bio: "Pioneer of computer programming.",
      location: "New York",
      website: "https://example.com",
    },
  },
};
