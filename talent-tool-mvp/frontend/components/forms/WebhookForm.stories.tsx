import type { Meta, StoryObj } from "@storybook/nextjs";
import { WebhookForm } from "./WebhookForm";

const meta: Meta<typeof WebhookForm> = {
  title: "Forms/WebhookForm",
  component: WebhookForm,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof WebhookForm>;

const events = [
  { value: "candidate.created", label: "Candidate created" },
  { value: "candidate.updated", label: "Candidate updated" },
  { value: "match.ready", label: "Match ready" },
];

export const Default: Story = { args: { onSubmit: async (v) => console.log(v), eventOptions: events } };
