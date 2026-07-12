import type { Meta, StoryObj } from "@storybook/nextjs";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./tabs";

const meta: Meta<typeof Tabs> = { title: "UI/Tabs", component: Tabs, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Tabs>;

export const Basic: Story = {
  render: () => (
    <Tabs defaultValue="overview" className="w-[400px]">
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="matches">Matches</TabsTrigger>
        <TabsTrigger value="notes">Notes</TabsTrigger>
      </TabsList>
      <TabsContent value="overview">Overview content</TabsContent>
      <TabsContent value="matches">Matches content</TabsContent>
      <TabsContent value="notes">Notes content</TabsContent>
    </Tabs>
  ),
};