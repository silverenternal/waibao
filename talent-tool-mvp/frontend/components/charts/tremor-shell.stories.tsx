import type { Meta, StoryObj } from "@storybook/react"
import {
  TremorShell,
  TremorKpiGrid,
  TremorKpiCard,
  TremorPanel,
  TremorDelta,
} from "./tremor-shell"

const meta: Meta<typeof TremorShell> = {
  title: "Charts/TremorShell",
  component: TremorShell,
  tags: ["autodocs"],
}
export default meta

type Story = StoryObj<typeof TremorShell>

export const Full: Story = {
  args: {
    title: "示例仪表盘",
    subtitle: "Tremor 风格的指标 + 面板",
    badge: "Demo",
  },
  render: (args) => (
    <TremorShell {...args}>
      <TremorKpiGrid>
        <TremorKpiCard title="P50 中位数" value={42} unit="k" delta={6} helper="YoY"
          spark={[20, 24, 28, 32, 36, 40, 42]} />
        <TremorKpiCard title="活跃用户" value={1240} delta={-3} helper="MoM"
          spark={[1300, 1340, 1320, 1280, 1260, 1240]} />
      </TremorKpiGrid>
      <TremorPanel title="趋势" description="最近 30 天">
        <TremorDelta delta={12} label="vs 上周" />
      </TremorPanel>
    </TremorShell>
  ),
}
