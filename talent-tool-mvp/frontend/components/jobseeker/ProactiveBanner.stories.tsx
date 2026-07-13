import type { Meta, StoryObj } from "@storybook/nextjs";
import { Bell, Megaphone, Rocket, Sparkles, Sun } from "lucide-react";

import { ProactiveBanner } from "./ProactiveBanner";

const meta: Meta<typeof ProactiveBanner> = {
  title: "Jobseeker/ProactiveBanner",
  component: ProactiveBanner,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  argTypes: {
    tone: {
      control: { type: "inline-radio" },
      options: ["info", "success", "warning", "danger", "calm"],
    },
    importance: {
      control: { type: "inline-radio" },
      options: ["status", "alert"],
    },
    icon: { control: false },
    onAction: { action: "action" },
    onSecondary: { action: "secondary" },
    onDismiss: { action: "dismiss" },
  },
  decorators: [
    (Story) => (
      <div className="w-[640px] max-w-full">
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof ProactiveBanner>;

export const Info: Story = {
  args: {
    title: "你有一份新的面试评估待查看",
    description: "Lyra Tech · 高级前端工程师 · 3 分钟前结束",
    tone: "info",
    icon: <Bell className="h-5 w-5" />,
    actionLabel: "查看",
    secondaryLabel: "稍后提醒",
    dismissible: true,
    badge: "刚刚",
  },
};

export const Success: Story = {
  args: {
    title: "太好了！你的面试已经被 2 位招聘官标记为「想继续」",
    description: "下一步：为他们撰写一份个性化跟进信，我们已经准备好了模板。",
    tone: "success",
    icon: <Sparkles className="h-5 w-5" />,
    actionLabel: "生成跟进信",
    secondaryLabel: "稍后",
    badge: "推荐",
  },
};

export const Warning: Story = {
  args: {
    title: "你的简历已经 30 天没更新了",
    description: "招聘官更愿意联系最近活跃的候选人 —— 现在只需 1 分钟。",
    tone: "warning",
    icon: <Sun className="h-5 w-5" />,
    actionLabel: "立即更新",
  },
};

export const Danger: Story = {
  args: {
    title: "我们注意到你最近情绪波动较大",
    description: "如果想找个人聊聊，HR 团队随时在这里。一切匿名且自愿。",
    tone: "danger",
    icon: <Megaphone className="h-5 w-5" />,
    actionLabel: "预约关怀通话",
    secondaryLabel: "了解更多",
    importance: "alert",
  },
};

export const Calm: Story = {
  args: {
    title: "试试我们新出的「技能魔方」",
    description: "根据你最近的匹配度，30 秒生成一份个性化能力图谱。",
    tone: "calm",
    icon: <Rocket className="h-5 w-5" />,
    actionLabel: "开始试用",
    secondaryLabel: "不再提醒",
    dismissible: true,
  },
};

export const WithoutCTA: Story = {
  args: {
    title: "本周共 12 位招聘官查看了你的主页",
    description: "他们暂时没有联系你 —— 你可以选择主动出击。",
    tone: "calm",
    dismissible: true,
  },
};
