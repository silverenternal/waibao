import type { Meta, StoryObj } from "@storybook/nextjs";
import { TicketForm } from "./TicketForm";

const meta: Meta<typeof TicketForm> = {
  title: "Forms/TicketForm",
  component: TicketForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof TicketForm>;

export const Default: Story = { args: { onSubmit: async (v) => console.log(v) } };
export const Urgent: Story = {
  args: { onSubmit: async (v) => console.log(v), defaultValues: { priority: "urgent" } },
};
