import type { Meta, StoryObj } from "@storybook/nextjs";
import FollowUpQuestions from "./FollowUpQuestions";

const meta: Meta<typeof FollowUpQuestions> = { title: "Components/FollowUpQuestions", component: FollowUpQuestions, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof FollowUpQuestions>;

export const Default: Story = { args: { questions: ["What salary are you targeting?", "Can you start in 4 weeks?"] } };
export const Empty: Story = { args: { questions: [] } };