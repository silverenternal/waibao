import type { Meta, StoryObj } from "@storybook/nextjs";
import NegotiationScript from "./NegotiationScript";

const meta: Meta<typeof NegotiationScript> = { title: "Components/NegotiationScript", component: NegotiationScript, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof NegotiationScript>;

export const Default: Story = { args: { script: "Thanks for the offer. Based on market data, I'd like to discuss the base." } };