import type { Meta, StoryObj } from "@storybook/react"
import { PSDetectionBadge, PSDetectionBreakdown } from "./PSDetectionBadge"

const meta: Meta<typeof PSDetectionBadge> = {
  title: "Compliance/PSDetectionBadge",
  component: PSDetectionBadge,
  tags: ["autodocs"],
}
export default meta

type Story = StoryObj<typeof PSDetectionBadge>

export const Clean: Story = { args: { suspicion: 0.1 } }
export const Watch: Story = { args: { suspicion: 0.4 } }
export const Review: Story = { args: { suspicion: 0.7 } }
export const Tampered: Story = { args: { suspicion: 0.92, escalated: true } }

export const WithBreakdown: Story = {
  args: {
    suspicion: 0.82,
    findings: [
      { code: "ela", label: "ELA 噪点不均", severity: 0.85, detail: "伪影残留" },
      { code: "exif", label: "Photoshop 软件指纹", severity: 0.72 },
    ],
  },
  render: (args) => (
    <div className="space-y-2">
      <PSDetectionBadge {...args} />
      <PSDetectionBreakdown findings={args.findings ?? []} />
    </div>
  ),
}
