"use client";

/**
 * Refine i18nProvider — bridges Refine's translation keys with next-intl.
 *
 * Three locales: zh-CN (default), en-US, ja-JP.
 *
 * We hand-roll the dictionaries for the keys Refine emits (actions, buttons,
 * table headers) so we don't pull in another npm package. The user-facing copy
 * stays in `messages/{locale}.json` (next-intl) for app-specific strings.
 */

import type { I18nProvider } from "@refinedev/core";

type Locale = "zh-CN" | "en-US" | "ja-JP";

const DICT: Record<Locale, Record<string, string>> = {
  "zh-CN": {
    "actions.add": "新增",
    "actions.create": "创建",
    "actions.delete": "删除",
    "actions.edit": "编辑",
    "actions.show": "查看",
    "actions.refresh": "刷新",
    "actions.save": "保存",
    "actions.cancel": "取消",
    "actions.list": "列表",
    "buttons.delete": "删除",
    "buttons.edit": "编辑",
    "buttons.create": "新建",
    "buttons.save": "保存",
    "buttons.cancel": "取消",
    "buttons.filter": "筛选",
    "buttons.clear": "清除",
    "buttons.export": "导出",
    "buttons.import": "导入",
    "buttons.search": "搜索",
    "table.actions": "操作",
    "table.noResults": "暂无数据",
    "warnWhenUnsavedChanges": "您有未保存的修改,确定离开?",
    "notifications.createSuccess": "创建成功",
    "notifications.createError": "创建失败",
    "notifications.updateSuccess": "更新成功",
    "notifications.updateError": "更新失败",
    "notifications.deleteSuccess": "删除成功",
    "notifications.deleteError": "删除失败",
  },
  "en-US": {
    "actions.add": "Add",
    "actions.create": "Create",
    "actions.delete": "Delete",
    "actions.edit": "Edit",
    "actions.show": "Show",
    "actions.refresh": "Refresh",
    "actions.save": "Save",
    "actions.cancel": "Cancel",
    "actions.list": "List",
    "buttons.delete": "Delete",
    "buttons.edit": "Edit",
    "buttons.create": "Create",
    "buttons.save": "Save",
    "buttons.cancel": "Cancel",
    "buttons.filter": "Filter",
    "buttons.clear": "Clear",
    "buttons.export": "Export",
    "buttons.import": "Import",
    "buttons.search": "Search",
    "table.actions": "Actions",
    "table.noResults": "No results",
    "warnWhenUnsavedChanges": "You have unsaved changes. Leave anyway?",
    "notifications.createSuccess": "Created successfully",
    "notifications.createError": "Create failed",
    "notifications.updateSuccess": "Updated successfully",
    "notifications.updateError": "Update failed",
    "notifications.deleteSuccess": "Deleted successfully",
    "notifications.deleteError": "Delete failed",
  },
  "ja-JP": {
    "actions.add": "追加",
    "actions.create": "作成",
    "actions.delete": "削除",
    "actions.edit": "編集",
    "actions.show": "表示",
    "actions.refresh": "更新",
    "actions.save": "保存",
    "actions.cancel": "キャンセル",
    "actions.list": "一覧",
    "buttons.delete": "削除",
    "buttons.edit": "編集",
    "buttons.create": "新規",
    "buttons.save": "保存",
    "buttons.cancel": "キャンセル",
    "buttons.filter": "絞込",
    "buttons.clear": "クリア",
    "buttons.export": "エクスポート",
    "buttons.import": "インポート",
    "buttons.search": "検索",
    "table.actions": "操作",
    "table.noResults": "データなし",
    "warnWhenUnsavedChanges": "未保存の変更があります。離れますか?",
    "notifications.createSuccess": "作成しました",
    "notifications.createError": "作成に失敗しました",
    "notifications.updateSuccess": "更新しました",
    "notifications.updateError": "更新に失敗しました",
    "notifications.deleteSuccess": "削除しました",
    "notifications.deleteError": "削除に失敗しました",
  },
};

function resolveLocale(locale?: string): Locale {
  if (locale === "en" || locale === "en-US") return "en-US";
  if (locale === "ja" || locale === "ja-JP") return "ja-JP";
  return "zh-CN";
}

export const i18nProvider: I18nProvider = {
  translate: (key: string, options?: any, locale?: string) => {
    const dict = DICT[resolveLocale(locale)];
    let value = dict[key];
    if (typeof value !== "string") value = key;
    if (options && typeof value === "string") {
      for (const [k, v] of Object.entries(options)) {
        value = value.replace(new RegExp(`{{\\s*${k}\\s*}}`, "g"), String(v));
      }
    }
    return value;
  },
  changeLocale: (locale: string) => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("refine-locale", locale);
      } catch {
        // ignore
      }
    }
    return Promise.resolve();
  },
  getLocale: () => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("refine-locale");
      if (saved) return saved;
    }
    if (typeof navigator !== "undefined" && navigator.language) {
      return resolveLocale(navigator.language);
    }
    return "zh-CN";
  },
};

export default i18nProvider;
