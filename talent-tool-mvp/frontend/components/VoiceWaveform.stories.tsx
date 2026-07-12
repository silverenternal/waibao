import type { Meta, StoryObj } from "@storybook/nextjs";
import VoiceWaveform from "./VoiceWaveform";

const meta: Meta<typeof VoiceWaveform> = { title: "Components/VoiceWaveform", component: VoiceWaveform, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof VoiceWaveform>;

export const Default: Story = { args: { samples: [0.1, 0.4, 0.6, 0.3, 0.2, 0.8, 0.5] } };
export const Flat: Story = { args: { samples: [0.1, 0.1, 0.1] } };