import type { Meta, StoryObj } from "@storybook/react";
import { Markdown } from "./Markdown";

const meta: Meta<typeof Markdown> = {
  title: "Shared/Markdown",
  component: Markdown,
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Shared renderer for LLM / agent generated markdown. GFM (tables, lists, headings), explicit Tailwind element styles (no @tailwindcss/typography plugin), and XSS-safe — no raw-HTML injection (no __html prop, no rehype-raw), so inline HTML in untrusted LLM output is not executed.",
      },
    },
  },
};
export default meta;

type Story = StoryObj<typeof Markdown>;

const RICH = `## 匹配理由
- **技能匹配** 5/5：TypeScript / React / Node 全覆盖
- 同城（北京），可立即到岗
- 薪资期望 *符合* 区间

| 维度 | 候选人 | 岗位要求 |
| --- | --- | --- |
| 经验 | 8 年 | 5+ 年 |
| 学历 | 本科 | 本科 |

> 综合画像相近，建议优先沟通。`;

export const Rich: Story = {
  args: { children: RICH, size: "sm" },
};

export const PlainText: Story = {
  args: { children: "智能体未给出 markdown，只是一句普通文本。" },
};

export const Empty: Story = {
  args: { children: "" },
};

export const UnsafeHtml: Story = {
  name: "Inline HTML not executed (XSS-safe)",
  args: {
    children: `正文内容。
<img src="x" onerror="alert(1)" />
<script>alert(2)</script>
这部分 **粗体** 仍正常渲染，但上面的 img/script 不会执行。`,
  },
};
