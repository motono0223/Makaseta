import { FormEvent, useCallback, useState } from "react";
import { Message, Plan, Project, Task, api } from "../api";
import { PRIORITY } from "../labels";
import { usePolling } from "../usePolling";
import Markdown from "./Markdown";
import MessageList from "./MessageList";
import { useThread } from "./ThreadDrawer";

const PLAN_STATUS: Record<Plan["status"], string> = {
  drafting: "計画中",
  proposed: "承認待ち",
  approved: "承認済み",
  cancelled: "取り消し",
};

/** Requests to the project's contact manager, the plans that come back, and everything said about the project. */
export default function ProjectThread({ project, tasks, onChanged }: { project: Project; tasks: Task[]; onChanged: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const openThread = useThread();

  const load = useCallback(() => {
    api.projectThread(project.id).then(setMessages).catch(() => undefined);
    api.plans(project.id).then(setPlans).catch(() => undefined);
  }, [project.id]);
  const busyWork = tasks.some((t) => t.status === "in_progress") || plans.some((p) => p.status === "drafting");
  usePolling(load, busyWork ? 3000 : 8000);

  const agents = new Map(project.members.map((m) => [m.agent.id, m.agent]));
  const primary = project.members.find((m) => m.is_primary);
  const question = [...messages].reverse().find((m) => m.awaiting_answer);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setText("");
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function send(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    if (question?.run_id) act(() => api.answerRun(question.run_id!, text));
    else act(() => api.requestToManager(project.id, text));
  }

  const open = plans.filter((p) => p.status === "drafting" || p.status === "proposed");

  return (
    <div className="thread-layout">
      {error && <p className="status bad">{error}</p>}
      {open.map((plan) => (
        <PlanCard key={plan.id} plan={plan} busy={busy} onAct={act} />
      ))}

      <section className="card thread-card">
        <MessageList messages={messages} agents={agents} />
        <form className="composer" onSubmit={send}>
          {question ? (
            <p className="small status bad">
              {agents.get(question.agent_id ?? 0)?.name}さんの質問に回答します
            </p>
          ) : primary ? (
            <p className="small muted">
              窓口の
              <button type="button" className="link-button small" onClick={() => openThread(primary.agent.id)}>
                {primary.agent.name}さん
              </button>
              に依頼します。{primary.agent.name}さんがタスクに分けた計画を提案し、承認すると作業が始まります。
            </p>
          ) : (
            <p className="small status bad">窓口のマネージャーがいません。設定タブでマネージャーをアサインしてください。</p>
          )}
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={question ? "回答を入力" : "例: 出張規程の改定案と新旧比較表を作ってください"}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(e);
            }} />
          <div className="form-actions">
            <button type="submit" className="btn primary" disabled={busy || !text.trim() || (!question && !primary)}>
              {question ? "回答する" : "依頼する"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export function PlanCard({ plan, busy, onAct }: { plan: Plan; busy: boolean; onAct: (a: () => Promise<unknown>) => void }) {
  const [comment, setComment] = useState("");
  const failed = plan.run_status === "failed" || plan.run_status === "interrupted";
  return (
    <section className={`card plan-card plan-${plan.status}`}>
      <div className="inbox-head">
        <span className="badge inbox-badge-plan">{PLAN_STATUS[plan.status]}</span>
        <strong className="grow">依頼: {plan.request.split("\n")[0]}</strong>
      </div>
      {plan.status === "drafting" && !failed && (
        <p className="muted">
          {plan.run_status === "waiting" ? "マネージャーが質問しています（下のスレッドで回答してください）。" : "マネージャーが計画を立てています…"}
        </p>
      )}
      {failed && (
        <div className="form-actions">
          <span className="status bad small">{plan.run_error}</span>
          <button type="button" className="btn" disabled={busy} onClick={() => onAct(() => api.retryPlan(plan.id))}>再実行</button>
        </div>
      )}
      {plan.status === "proposed" && (
        <>
          <Markdown>{plan.summary}</Markdown>
          <ol className="plan-items">
            {plan.items.map((item, i) => (
              <li key={i}>
                <div>
                  <strong>{item.title}</strong>
                  <span className="muted small">
                    {" "}→ {item.assignee_name ?? "（担当不明）"}
                    {item.reviewer_name && `（レビュー: ${item.reviewer_name}）`}
                    {item.priority !== "normal" && ` · 優先度 ${PRIORITY[item.priority]}`}
                    {item.depends_on.length > 0 && ` · ${item.depends_on.map((d) => `${d}番`).join("・")}の後`}
                  </span>
                </div>
                <div className="muted small pre-line">{item.instructions}</div>
              </li>
            ))}
            <li className="muted small">全部終わったら、マネージャーが取りまとめて報告します。</li>
          </ol>
          <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)}
            placeholder="差し戻す場合は、直してほしい点を書いてください" />
          <div className="form-actions">
            <button type="button" className="btn primary" disabled={busy} onClick={() => onAct(() => api.approvePlan(plan.id))}>
              承認して開始
            </button>
            <button type="button" className="btn" disabled={busy || !comment.trim()}
              onClick={() => onAct(() => api.rejectPlan(plan.id, comment))}>
              差し戻す
            </button>
            <button type="button" className="btn danger push-right" disabled={busy}
              onClick={() => window.confirm("この依頼を取り消しますか？") && onAct(() => api.cancelPlan(plan.id))}>
              取り消す
            </button>
          </div>
        </>
      )}
    </section>
  );
}
