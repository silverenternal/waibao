import type { Meta, StoryObj } from "@storybook/react"
import { ToneSimulator } from "./ToneSimulator"

const meta: Meta<typeof ToneSimulator> = {
  title: "HR/ToneSimulator",
  component: ToneSimulator,
  tags: ["autodocs"],
}
export default meta

type Story = StoryObj<typeof ToneSimulator>

export const Default: Story = {
  args: {
    userId: "demo",
    history: ["请您按时提交周报,我们一起 review。", "Q3 增长 30%。"],
  },
}
