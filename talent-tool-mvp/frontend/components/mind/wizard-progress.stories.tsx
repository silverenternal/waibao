import type { Meta, StoryObj } from "@storybook/nextjs";
import { WizardProgress } from "./wizard-progress";

const meta: Meta<typeof WizardProgress> = { title: "Mind/WizardProgress", component: WizardProgress, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof WizardProgress>;

export const Default: Story = { args: { currentStep: 2, totalSteps: 5 } };
export const Complete: Story = { args: { currentStep: 5, totalSteps: 5 } };