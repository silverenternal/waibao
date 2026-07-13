import type { Meta, StoryObj } from "@storybook/nextjs";
import { Brain, Coffee, Sparkles } from "lucide-react";

import { CareCard } from "./CareCard";

const meta: Meta<typeof CareCard> = {
  title: "Jobseeker/CareCard",
  component: CareCard,
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
  },
  argTypes: {
    tone: {
      control: { type: "select" },
      options: ["info", "success", "warning", "danger", "calm"],
    },
    badge: { control: false },
    items: { control: false },
    icon: { control: false },
    onAction: { action: "action" },
    onDismiss: { action: "dismiss" },
  },
  decorators: [
    (Story) => (
      <div className="w-[420px] max-w-full">
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof CareCard>;

export const Default: Story = {
  args: {
    title: "你今天看起来有点疲惫，要不要先休息一下？",
    description: "我们已经保存了你的进度，可以随时回来继续。",
    tone: "calm",
    actionLabel: "看看放松建议",
    onAction: () => {},
  },
};

export const DangerTone: Story = {
  args: {
    title: "我们注意到你最近情绪有些波动",
    description: "如果想找个人聊聊，HR 团队随时在这里。",
    tone: "danger",
    badge: { label: "隐私 · 仅你可见", tone: "outline" },
    actionLabel: "预约一次关怀通话",
    onAction: () => {},
    dismissible: true,
    onDismiss: () => {},
  },
};

export const WithItems: Story = {
  args: {
    title: "今日为你准备了三件小事",
    description: "完成任意一项都可以获得积分奖励。",
    tone: "info",
    items: [
      {
        id: "1",
        title: "更新一段最近的工作经历",
        description: "大约 3 分钟",
        icon: <Brain className="h-4 w-4" />,
        tags: ["推荐"],
      },
      {
        id: "2",
        title: "试试我们新出的「技能魔方」",
        description: "根据你当前的匹配度推荐",
        icon: <Sparkles className="h-4 w-4" />,
        tags: ["新功能"],
      },
      {
        id: "3",
        title: "今天先休息也可以",
        description: "你最近 7 天都很努力",
        icon: <Coffee className="h-4 w-4" />,
      },
    ],
    actionLabel: "全部查看",
    onAction: () => {},
  },
};

export const SuccessTone: Story = {
  args: {
    title: "你的简历已经被 3 位招聘官收藏",
    description: "他们可能会在 24 小时内联系你。",
    tone: "success",
    actionLabel: "查看动态",
    onAction: () => {},
    dismissible: true,
    onDismiss: () => {},
  },
};

export const WarningTone: Story = {
  args: {
    title: "你的简历已经 45 天没有更新了",
    description: "招聘官更愿意联系最近活跃的候选人。",
    tone: "warning",
    actionLabel: "立即更新",
    onAction: () => {},
  },
};

export const WithChildren: Story = {
  args: {
    title: "你愿意和我们的健康顾问聊聊吗？",
    description: "通话时长大约 15 分钟，完全匿名。",
    tone: "calm",
    children: (
      <p className="rounded-md bg-background/60 p-2 text-xs text-muted-foreground">
        提示：所有通话内容仅用于改善你的求职体验，不会上报到你的雇主。
      </p>
    ),
    actionLabel: "预约",
    onAction: () => {},
  },
};
