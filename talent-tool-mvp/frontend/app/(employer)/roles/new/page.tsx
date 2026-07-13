"use client";

import * as React from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { JDTemplatePicker } from "@/components/jd/JDTemplatePicker";
import { JDScorer } from "@/components/jd/JDScorer";
import { ChevronLeft, Wand2, Save } from "lucide-react";

export default function NewRolePage() {
  const [title, setTitle] = React.useState("");
  const [department, setDepartment] = React.useState("技术");
  const [location, setLocation] = React.useState("北京");
  const [description, setDescription] = React.useState("");

  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-2">
        <Button variant="ghost" size="sm" asChild className="self-start">
          <Link href="/employer/roles">
            <ChevronLeft className="mr-1 h-4 w-4" /> 返回 Roles
          </Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight md:text-3xl">新建岗位</h1>
        <p className="text-sm text-muted-foreground">从模板开始,或者先让 AI 帮你起一稿。</p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="text-xs">岗位名</label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="如 高级前端工程师"
                />
              </div>
              <div>
                <label className="text-xs">部门</label>
                <Select value={department} onValueChange={(v) => v && setDepartment(v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="技术">技术</SelectItem>
                    <SelectItem value="产品">产品</SelectItem>
                    <SelectItem value="市场">市场</SelectItem>
                    <SelectItem value="运营">运营</SelectItem>
                    <SelectItem value="财务">财务</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs">工作地</label>
                <Select value={location} onValueChange={(v) => v && setLocation(v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="北京">北京</SelectItem>
                    <SelectItem value="上海">上海</SelectItem>
                    <SelectItem value="杭州">杭州</SelectItem>
                    <SelectItem value="深圳">深圳</SelectItem>
                    <SelectItem value="Remote">Remote</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs">HC</label>
                <Input type="number" placeholder="如 1" defaultValue={1} />
              </div>
            </div>
            <div>
              <label className="text-xs">描述 (开篇)</label>
              <Textarea
                rows={5}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="我们正在构建 X,改变 Y…"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button>
                <Wand2 className="mr-1 h-4 w-4" />
                AI 草稿
              </Button>
              <Button variant="outline">
                <Save className="mr-1 h-4 w-4" />
                保存草稿
              </Button>
            </div>
            <Badge variant="secondary">下一步:营销化 → 发布</Badge>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">模板</CardTitle>
            </CardHeader>
            <CardContent>
              <JDTemplatePicker />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">JD 评分</CardTitle>
            </CardHeader>
            <CardContent>
              <JDScorer />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
