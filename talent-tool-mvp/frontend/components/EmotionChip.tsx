"use client";

const COLOR: Record<string, string> = {
  joy: "#10b981",
  sadness: "#6366f1",
  anger: "#ef4444",
  fear: "#f59e0b",
  surprise: "#8b5cf6",
  disgust: "#84cc16",
  neutral: "#94a3b8",
};

const LABEL: Record<string, string> = {
  joy: "开心",
  sadness: "难过",
  anger: "愤怒",
  fear: "焦虑",
  surprise: "惊讶",
  disgust: "厌恶",
  neutral: "平静",
};

export function EmotionChip({ emotion, intensity }: { emotion?: string; intensity?: number }) {
  if (!emotion) return null;
  return (
    <span
      className="inline-flex items-center px-3 py-1 rounded-full text-xs text-white font-medium"
      style={{ background: COLOR[emotion] || COLOR.neutral }}
    >
      {LABEL[emotion] || emotion}
      {intensity !== undefined && (
        <span className="ml-1 opacity-75">{Math.round(intensity * 100)}%</span>
      )}
    </span>
  );
}

export function EmotionBar({ emotion, intensity }: { emotion?: string; intensity?: number }) {
  if (!emotion || intensity === undefined) return null;
  return (
    <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
      <div
        className="h-full transition-all"
        style={{
          width: `${intensity * 100}%`,
          background: COLOR[emotion] || COLOR.neutral,
        }}
      />
    </div>
  );
}