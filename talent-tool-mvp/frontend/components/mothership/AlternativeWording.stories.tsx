import type { Meta, StoryObj } from "@storybook/nextjs";
import { AlternativeWording } from "./AlternativeWording";

const meta: Meta<typeof AlternativeWording> = { title: "Mothership/AlternativeWording", component: AlternativeWording, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof AlternativeWording>;

export const Default: Story = { args: { original: "5 years experience", alternatives: ["5+ years experience", "5 years' experience"] } };