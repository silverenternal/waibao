import type { Meta, StoryObj } from "@storybook/nextjs";
import { WizardStepReview } from "./wizard-step-review";

const meta: Meta<typeof WizardStepReview> = { title: "Mind/WizardStepReview", component: WizardStepReview, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof WizardStepReview>;

export const Default: Story = { args: { title: "Senior Designer", description: "Lead the design system.", location: "London" } };