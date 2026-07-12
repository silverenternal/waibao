"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Trash2, Plus } from "lucide-react";
import type { SubscriptionBody } from "@/lib/types";

interface SubscriptionFormProps {
  initial?: Partial<SubscriptionBody>;
  onSubmit: (body: SubscriptionBody) => Promise<void> | void;
  onCancel?: () => void;
  submitting?: boolean;
}

const CHANNELS = [
  { value: "web", label: "In-app" },
  { value: "email", label: "Email" },
  { value: "dingtalk", label: "DingTalk" },
  { value: "feishu", label: "Feishu" },
  { value: "webhook", label: "Webhook" },
];

const REMOTE_OPTIONS = [
  { value: "", label: "Any" },
  { value: "onsite", label: "Onsite" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote" },
];

const SENIORITY_OPTIONS = [
  { value: "", label: "Any" },
  { value: "junior", label: "Junior" },
  { value: "mid", label: "Mid" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
  { value: "principal", label: "Principal" },
];

export function SubscriptionForm({
  initial,
  onSubmit,
  onCancel,
  submitting,
}: SubscriptionFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [role, setRole] = useState(initial?.criteria?.role ?? "");
  const [city, setCity] = useState(initial?.criteria?.city ?? "");
  const [salaryMin, setSalaryMin] = useState(
    String(initial?.criteria?.salary_min ?? ""),
  );
  const [currency, setCurrency] = useState(
    initial?.criteria?.currency ?? "CNY",
  );
  const [skills, setSkills] = useState<string[]>(
    initial?.criteria?.skills ?? [],
  );
  const [skillDraft, setSkillDraft] = useState("");
  const [seniority, setSeniority] = useState(
    initial?.criteria?.seniority ?? "",
  );
  const [remote, setRemote] = useState(initial?.criteria?.remote_policy ?? "");
  const [channels, setChannels] = useState<string[]>(
    initial?.channels ?? ["web"],
  );

  const handleSelectString = (
  setter: (v: string) => void,
) => (value: unknown) => {
  // shadcn Select's onValueChange passes string | null
  setter((value as string | null) ?? "");
};

const addSkill = () => {
    const v = skillDraft.trim();
    if (!v) return;
    if (skills.includes(v)) {
      setSkillDraft("");
      return;
    }
    setSkills([...skills, v]);
    setSkillDraft("");
  };

  const removeSkill = (s: string) => {
    setSkills(skills.filter((x) => x !== s));
  };

  const toggleChannel = (c: string, on: boolean) => {
    setChannels(
      on ? Array.from(new Set([...channels, c])) : channels.filter((x) => x !== c),
    );
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const body: SubscriptionBody = {
      name: name.trim(),
      criteria: {
        role: role.trim(),
        city: city.trim(),
        salary_min: Number(salaryMin) || 0,
        currency,
        skills,
        seniority,
        remote_policy: remote,
      },
      channels: channels.length > 0 ? channels : ["web"],
    };
    await onSubmit(body);
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="sub-name">Subscription name</Label>
        <Input
          id="sub-name"
          placeholder="e.g. Shanghai senior Python"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="sub-role">Role keyword</Label>
          <Input
            id="sub-role"
            placeholder="backend, PM, ..."
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="sub-city">City</Label>
          <Input
            id="sub-city"
            placeholder="Shanghai / Remote / ..."
            value={city}
            onChange={(e) => setCity(e.target.value)}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="sub-salary">Min salary</Label>
          <Input
            id="sub-salary"
            type="number"
            min={0}
            placeholder="0"
            value={salaryMin}
            onChange={(e) => setSalaryMin(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="sub-currency">Currency</Label>
          <Select
            value={currency}
            onValueChange={handleSelectString(setCurrency)}
          >
            <SelectTrigger id="sub-currency">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="CNY">CNY</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
              <SelectItem value="SGD">SGD</SelectItem>
              <SelectItem value="GBP">GBP</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Seniority</Label>
          <Select
            value={seniority}
            onValueChange={handleSelectString(setSeniority)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SENIORITY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Remote policy</Label>
          <Select
            value={remote}
            onValueChange={handleSelectString(setRemote)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REMOTE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1">
        <Label>Required skills</Label>
        <div className="flex gap-2">
          <Input
            placeholder="python"
            value={skillDraft}
            onChange={(e) => setSkillDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addSkill();
              }
            }}
          />
          <Button type="button" variant="outline" size="icon" onClick={addSkill}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        {skills.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {skills.map((s) => (
              <span
                key={s}
                className="inline-flex items-center gap-1 rounded-full bg-blue-50 text-blue-700 px-2 py-0.5 text-xs"
              >
                {s}
                <button
                  type="button"
                  className="hover:text-red-600"
                  onClick={() => removeSkill(s)}
                  aria-label={`Remove ${s}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <Label>Notify me on</Label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {CHANNELS.map((c) => (
            <label
              key={c.value}
              className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-pointer hover:bg-muted"
            >
              <Checkbox
                checked={channels.includes(c.value)}
                onCheckedChange={(v) => toggleChannel(c.value, Boolean(v))}
              />
              {c.label}
            </label>
          ))}
        </div>
      </div>

      <div className="flex gap-2 pt-2">
        <Button type="submit" disabled={submitting || !name.trim()}>
          {submitting ? "Saving..." : "Save subscription"}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}