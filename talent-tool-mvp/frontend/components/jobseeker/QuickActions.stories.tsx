import type { Meta, StoryObj } from "@storybook/nextjs";
import {
  Briefcase,
  FileText,
  Heart,
  MessageCircle,
  RefreshCw,
  Sparkles,
  Upload,
  Wallet,
} from "lucide-react";

import { QuickActions } from "./QuickActions";

const meta: Meta<typeof QuickActions> = {
  title: "Jobseeker/QuickActions",
  component: QuickActions,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  argTypes: {
    columns: {
      control: { type: "inline-radio" },
      options: [2, 3, 4],
    },
    actions: { control: false },
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

type Story = StoryObj<typeof QuickActions>;

const baseActions = [
  {
    id: "resume",
    label: "上传最新简历",
    description: "约 1 分钟",
    icon: Upload,
  },
  {
    id: "match",
    label: "查看今日匹配",
    description: "12 个新机会",
    icon: Sparkles,
    badge: "新",
  },
  {
    id: "refer",
    label: "邀请朋友内推",
    description: "成功入职奖励 ¥800",
    icon: Heart,
  },
  {
    id: "salary",
    label: "查看薪酬洞察",
    description: "同岗位中位数",
    icon: Wallet,
  },
];

export const Default: Story = {
  args: {
    title: "今天可以做的事",
    columns: 3,
    actions: baseActions,
  },
};

export const TwoColumns: Story = {
  args: {
    title: "常用操作",
    columns: 2,
    actions: [
      {
        id: "messages",
        label: "查看消息",
        description: "3 条未读",
        icon: MessageCircle,
        badge: "3",
      },
      {
        id: "interviews",
        label: "面试安排",
        description: "本周 2 场",
        icon: Briefcase,
      },
      {
        id: "documents",
        label: "我的文档",
        description: "简历 / 作品集",
        icon: FileText,
      },
      {
        id: "refresh",
        label: "刷新匹配",
        description: "基于最新简历",
        icon: RefreshCw,
      },
    ],
  },
};

export const FourColumns: Story = {
  args: {
    title: "一栏搞定",
    columns: 4,
    actions: baseActions,
  },
};

export const WithLinks: Story = {
  args: {
    title: "快捷入口",
    columns: 3,
    actions: [
      {
        id: "resume-link",
        label: "我的简历",
        icon: FileText,
        href: "/jobseeker/account",
      },
      {
        id: "match-link",
        label: "今日匹配",
        icon: Sparkles,
        href: "/jobseeker/plan",
      },
      {
        id: "refer-link",
        label: "邀请朋友",
        icon: Heart,
        href: "/jobseeker/refer",
      },
    ],
  },
};

export const WithDisabled: Story = {
  args: {
    title: "稍后可用",
    columns: 3,
    actions: [
      {
        id: "a",
        label: "刷新匹配",
        icon: RefreshCw,
        description: "刚刚才运行过",
        disabled: true,
      },
      {
        id: "b",
        label: "上传作品集",
        icon: Upload,
        description: "需要先完成简历",
        disabled: true,
      },
      {
        id: "c",
        label: "查看消息",
        icon: MessageCircle,
      },
    ],
  },
};
