import type { Meta, StoryObj } from "@storybook/nextjs";
import { WizardStepDescription } from "./wizard-step-description";

const meta: Meta<typeof WizardStepDescription> = { title: "Mind/WizardStepDescription", component: WizardStepDescription, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof WizardStepDescription>;

export const Default: Story = { args: { value: "Lead the design system across product teams." } };
export const Empty: Story = { args: { value: "" } };