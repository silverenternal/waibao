import type { Meta, StoryObj } from "@storybook/react"
import { HRMetrics } from "./HRMetrics"

const meta: Meta<typeof HRMetrics> = {
  title: "Dashboard/HRMetrics",
  component: HRMetrics,
  tags: ["autodocs"],
}
export default meta

type Story = StoryObj<typeof HRMetrics>

export const Default: Story = { args: {} }

export const Loading: Story = { args: { loading: true } }

export const CustomData: Story = {
  args: {
    metrics: [
      { id: "1", label: "Test", value: 99, unit: "%", deltaPct: 5, tone: "emerald", icon: "clock" },
    ],
  },
}
