import type { Meta, StoryObj } from "@storybook/nextjs";

import { AIRecommendations } from "./AIRecommendations";

const meta: Meta<typeof AIRecommendations> = {
  title: "Jobseeker/AIRecommendations",
  component: AIRecommendations,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  argTypes: {
    tone: {
      control: { type: "inline-radio" },
      options: ["warm", "career", "growth"],
    },
    recommendations: { control: false },
  },
  decorators: [
    (Story) => (
      <div className="w-[720px] max-w-full">
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof AIRecommendations>;

const sampleRecommendations = [
  {
    id: "r1",
    title: "高级前端工程师",
    company: "Lyra Tech",
    matchScore: 92,
    badge: "热门",
    reasons: [
      "你的 8 年 React 经验与岗位要求完全匹配",
      "团队正在扩展视频协作业务线，与你最近的项目方向一致",
      "薪资区间高于你当前 18%",
    ],
    tags: ["React", "TypeScript", "远程友好"],
    ctaLabel: "查看岗位",
  },
  {
    id: "r2",
    title: "产品经理（AI Copilot）",
    company: "Nebula Labs",
    matchScore: 81,
    badge: "新发布",
    reasons: [
      "你近期主导的智能推荐项目与该产品方向高度吻合",
      "工作模式为混合办公，每周 2 天远程",
    ],
    tags: ["AI", "B 端"],
  },
  {
    id: "r3",
    title: "技术负责人",
    company: "Helios Studio",
    matchScore: 76,
    reasons: [
      "你的团队管理经验符合岗位需求",
      "公司处于 A 轮，发展空间大",
    ],
    tags: ["管理岗", "期权"],
  },
];

export const Default: Story = {
  args: {
    title: "今天为你精选的 3 个机会",
    description: "基于你最近的活跃度与偏好重新排序",
    tone: "career",
    recommendations: sampleRecommendations,
  },
};

export const WarmTone: Story = {
  args: {
    title: "根据你近期关注的方向",
    description: "我们多挑了一些偏关怀 / 长期发展的机会",
    tone: "warm",
    recommendations: sampleRecommendations,
  },
};

export const GrowthTone: Story = {
  args: {
    title: "想换个节奏？这些成长型岗位可能适合你",
    description: "成长曲线明显，最近 6 个月平均晋升周期 14 个月",
    tone: "growth",
    recommendations: sampleRecommendations.slice(0, 2),
  },
};

export const Empty: Story = {
  args: {
    title: "暂时没有合适的推荐",
    recommendations: [],
    emptyTitle: "暂时还没有合适的推荐",
    emptyDescription: "完善一下你的偏好与简历摘要，我们会重新计算。",
  },
};

export const WithLinksAndViewAll: Story = {
  args: {
    title: "今日匹配",
    description: "含 12 个新机会，按匹配度排序",
    tone: "career",
    recommendations: sampleRecommendations.map((r) => ({
      ...r,
      href: `/jobseeker/match/${r.id}`,
    })),
    onViewAll: () => {},
  },
};

export const SingleColumn: Story = {
  args: {
    title: "只想看一条",
    tone: "career",
    recommendations: sampleRecommendations.slice(0, 1),
  },
};
