import type { Meta, StoryObj } from "@storybook/nextjs";
import A11yLink from "./A11yLink";

const meta: Meta<typeof A11yLink> = {
  title: "UI/A11yLink",
  component: A11yLink,
  tags: ["autodocs"],
  argTypes: { href: { control: "text" } },
};
export default meta;
type Story = StoryObj<typeof A11yLink>;

export const Default: Story = { args: { href: "/candidates", children: "All candidates" } };
export const External: Story = { args: { href: "https://example.com", children: "External link", external: true } };