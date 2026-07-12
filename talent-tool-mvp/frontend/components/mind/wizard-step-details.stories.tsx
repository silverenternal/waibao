import type { Meta, StoryObj } from "@storybook/nextjs";
import { WizardStepDetails } from "./wizard-step-details";

const meta: Meta<typeof WizardStepDetails> = { title: "Mind/WizardStepDetails", component: WizardStepDetails, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof WizardStepDetails>;

export const Default: Story = { args: { location: "London", employmentType: "Full-time" } };
export const Remote: Story = { args: { location: "Remote", employmentType: "Contract" } };