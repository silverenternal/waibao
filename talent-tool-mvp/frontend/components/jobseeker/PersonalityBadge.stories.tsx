import type { Meta, StoryObj } from "@storybook/nextjs";

import {
  PersonalityBadge,
  PersonalityBadgeGroup,
} from "./PersonalityBadge";

const meta: Meta<typeof PersonalityBadge> = {
  title: "Jobseeker/PersonalityBadge",
  component: PersonalityBadge,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  argTypes: {
    size: {
      control: { type: "inline-radio" },
      options: ["sm", "default", "lg"],
    },
    trait: { control: false },
    onClick: { action: "badge-click" },
  },
  decorators: [
    (Story) => (
      <div className="p-2">
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof PersonalityBadge>;

const baseTrait = {
  code: "INTJ",
  label: "建筑师",
  description:
    "富有想象力且有战略头脑的思想家，所有事情都有一个改进的计划。",
  tone: "analyst" as const,
};

export const Default: Story = {
  args: {
    trait: baseTrait,
  },
};

export const Compact: Story = {
  args: {
    trait: baseTrait,
    codeOnly: true,
  },
};

export const Small: Story = {
  args: {
    trait: baseTrait,
    size: "sm",
    showDescription: true,
  },
};

export const Large: Story = {
  args: {
    trait: baseTrait,
    size: "lg",
  },
};

export const WithDescription: Story = {
  args: {
    trait: baseTrait,
    showDescription: true,
  },
};

export const AllTones: Story = {
  render: () => (
    <div className="flex max-w-md flex-wrap gap-2">
      <PersonalityBadge trait={{ code: "INTJ", label: "建筑师", tone: "analyst" }} />
      <PersonalityBadge trait={{ code: "INFJ", label: "提倡者", tone: "diplomat" }} />
      <PersonalityBadge trait={{ code: "ESTJ", label: "总经理", tone: "sentinel" }} />
      <PersonalityBadge trait={{ code: "ISTP", label: "鉴赏家", tone: "explorer" }} />
      <PersonalityBadge trait={{ code: "A1", label: "中性", tone: "neutral" }} />
    </div>
  ),
};

export const Interactive: Story = {
  args: {
    trait: baseTrait,
    showDescription: true,
  },
};

export const Group: Story = {
  render: () => (
    <PersonalityBadgeGroup
      title="你的性格画像"
      traits={[
        { code: "INTJ", label: "建筑师", tone: "analyst" },
        { code: "INFJ", label: "提倡者", tone: "diplomat" },
        { code: "ESTJ", label: "总经理", tone: "sentinel" },
        { code: "ISTP", label: "鉴赏家", tone: "explorer" },
      ]}
      showDescription
      size="default"
    />
  ),
};

export const GroupSmall: Story = {
  render: () => (
    <PersonalityBadgeGroup
      title="你最近的偏好"
      size="sm"
      traits={[
        { code: "REMOTE", label: "远程优先" },
        { code: "GROWTH", label: "成长型" },
        { code: "AI", label: "AI 方向", tone: "analyst" },
      ]}
    />
  ),
};
