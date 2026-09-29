import { Priority, ProjectStatus, TaskStatus } from "./api";

export const PROJECT_STATUS: Record<ProjectStatus, string> = {
  planning: "計画中",
  active: "進行中",
  paused: "一時停止",
  done: "完了",
  archived: "アーカイブ",
};

export const TASK_COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "backlog", label: "バックログ" },
  { status: "in_progress", label: "作業中" },
  { status: "waiting", label: "質問待ち" },
  { status: "review", label: "レビュー待ち" },
  { status: "done", label: "完了" },
];

export const TASK_STATUS: Record<TaskStatus, string> = Object.fromEntries(
  TASK_COLUMNS.map((c) => [c.status, c.label]),
) as Record<TaskStatus, string>;

export const PRIORITY: Record<Priority, string> = { high: "高", normal: "中", low: "低" };
