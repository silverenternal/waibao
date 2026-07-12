import type { Meta, StoryObj } from "@storybook/nextjs";
import RecommendedCandidate from "./RecommendedCandidate";

const meta: Meta<typeof RecommendedCandidate> = { title: "Components/RecommendedCandidate", component: RecommendedCandidate, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof RecommendedCandidate>;

export const Default: Story = { args: { name: "Sarah Lee", score: 92, reason: "Strong design systems background" } };
export const Lower: Story = { args: { name: "John Park", score: 71, reason: "Some overlap" } };