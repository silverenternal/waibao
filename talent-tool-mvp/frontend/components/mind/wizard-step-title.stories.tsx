import type { Meta, StoryObj } from "@storybook/nextjs";
import { WizardStepTitle } from "./wizard-step-title";

const meta: Meta<typeof WizardStepTitle> = { title: "Mind/WizardStepTitle", component: WizardStepTitle, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof WizardStepTitle>;

export const Default: Story = { args: { value: "Senior Designer" } };
export const Empty: Story = { args: { value: "" } };