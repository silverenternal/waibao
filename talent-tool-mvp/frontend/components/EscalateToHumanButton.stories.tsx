import type { Meta, StoryObj } from "@storybook/nextjs";
import EscalateToHumanButton from "./EscalateToHumanButton";

const meta: Meta<typeof EscalateToHumanButton> = { title: "Components/EscalateToHumanButton", component: EscalateToHumanButton, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EscalateToHumanButton>;

export const Default: Story = { args: {} };
export const Escalated: Story = { args: { escalated: true } };