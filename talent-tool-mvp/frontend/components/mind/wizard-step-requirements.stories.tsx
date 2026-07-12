import type { Meta, StoryObj } from "@storybook/nextjs";
import { WizardStepRequirements } from "./wizard-step-requirements";

const meta: Meta<typeof WizardStepRequirements> = { title: "Mind/WizardStepRequirements", component: WizardStepRequirements, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof WizardStepRequirements>;

export const Default: Story = { args: { skills: ["React", "TypeScript"], yearsExperience: 5 } };
export const Empty: Story = { args: { skills: [], yearsExperience: 0 } };