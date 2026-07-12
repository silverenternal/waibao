import type { Meta, StoryObj } from "@storybook/nextjs";
import { BiasExplanation } from "./BiasExplanation";

const meta: Meta<typeof BiasExplanation> = { title: "Mothership/BiasExplanation", component: BiasExplanation, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof BiasExplanation>;

export const Default: Story = { args: { explanation: "Words like 'aggressive' and 'rockstar' skew male-coded per the Gender Decoder corpus." } };