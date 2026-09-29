import { Agent } from "../api";

const LABELS = { idle: "待機中", working: "作業中", error: "エラー" } as const;

export default function StatusBadge({ agent }: { agent: Agent }) {
  if (!agent.active) return <span className="badge badge-on-leave">休暇中</span>;
  return <span className={`badge badge-${agent.status}`}>{LABELS[agent.status]}</span>;
}
