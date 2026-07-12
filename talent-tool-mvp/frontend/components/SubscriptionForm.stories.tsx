import type { Meta, StoryObj } from "@storybook/nextjs";
import SubscriptionForm from "./SubscriptionForm";

const meta: Meta<typeof SubscriptionForm> = { title: "Components/SubscriptionForm", component: SubscriptionForm, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SubscriptionForm>;

export const Default: Story = { args: {} };
export const Submitted: Story = { args: { submitted: true } };