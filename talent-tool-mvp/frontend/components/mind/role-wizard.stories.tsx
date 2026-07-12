import type { Meta, StoryObj } from "@storybook/nextjs";
import { RoleWizard } from "./role-wizard";

const meta: Meta<typeof RoleWizard> = { title: "Mind/RoleWizard", component: RoleWizard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof RoleWizard>;

export const Default: Story = { args: { step: 1, totalSteps: 5 } };
export const LastStep: Story = { args: { step: 5, totalSteps: 5 } };