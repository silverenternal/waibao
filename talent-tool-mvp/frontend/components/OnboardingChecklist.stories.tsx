import type { Meta, StoryObj } from "@storybook/nextjs";
import OnboardingChecklist from "./OnboardingChecklist";

const meta: Meta<typeof OnboardingChecklist> = { title: "Components/OnboardingChecklist", component: OnboardingChecklist, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof OnboardingChecklist>;

export const Default: Story = { args: { steps: [{ id: "1", label: "Complete profile", done: true }, { id: "2", label: "Connect ATS", done: false }] } };