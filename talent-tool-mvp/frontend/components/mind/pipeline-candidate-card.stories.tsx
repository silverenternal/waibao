import type { Meta, StoryObj } from "@storybook/nextjs";
import { PipelineCandidateCard } from "./pipeline-candidate-card";

const meta: Meta<typeof PipelineCandidateCard> = { title: "Mind/PipelineCandidateCard", component: PipelineCandidateCard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof PipelineCandidateCard>;

export const Default: Story = { args: { name: "Sarah Lee", stage: "Screening", score: 88 } };
export const OfferStage: Story = { args: { name: "John Park", stage: "Offer", score: 92 } };