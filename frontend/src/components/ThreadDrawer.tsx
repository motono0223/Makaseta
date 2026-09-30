import { ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Agent, Assignment, Message, Task, api } from "../api";
import { TASK_STATUS } from "../labels";
import { usePolling } from "../usePolling";
import Avatar from "./Avatar";
import MessageList from "./MessageList";
import StatusBadge from "./StatusBadge";

type OpenThread = (agentId: number, draft?: string) => void;
const ThreadContext = createContext<OpenThread>(() => undefined);

/** Open an agent's thread from anywhere: `openThread(agent.id)`, optionally with a message ready to send. */
export const useThread = () => useContext(ThreadContext);

export function ThreadProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState<{ agentId: number; draft: string } | null>(null);
  const openThread = useCallback<OpenThread>((agentId, draft = "") => setOpen({ agentId, draft }), []);
  return (
    <ThreadContext.Provider value={openThread}>
      {children}
      {open !== null && (
        <ThreadDrawer key={`${open.agentId}-${open.draft}`} agentId={open.agentId} draft={open.draft}
          onClose={() => setOpen(null)} />
      )}
    </ThreadContext.Provider>
  );
}

function ThreadDrawer({ agentId, draft, onClose }: { agentId: number; draft: string; onClose: () => void }) {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState(draft);
  const [asAnswer, setAsAnswer] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.agent(agentId).then(setAgent).catch((e: Error) => setError(e.message));
    api.assignments(agentId).then(setAssignments).catch(() => undefined);
    api.agentThread(agentId).then(setMessages).catch(() => undefined);
  }, [agentId]);

  const last = messages.at(-1);
  const awaitingReply = last?.sender === "manager" && last.kind === "chat";
  usePolling(load, awaitingReply || agent?.status === "working" ? 2000 : 5000);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tasks: (Task & { projectName: string })[] = assignments.flatMap((a) =>
    a.tasks.map((t) => ({ ...t, projectName: a.project_name })),
  );
  const openTasks = tasks.filter((t) => t.status !== "done");
  const doneTasks = tasks.filter((t) => t.status === "done");
  const question = [...messages].reverse().find((m) => m.awaiting_answer);

  async function send(e: { preventDefault: () => void }) {
    e.preventDefault();
    if (!text.trim()) return;
    setSending(true);
    setError(null);
    try {
      await api.messageAgent(agentId, text, question?.run_id && asAnswer ? question.run_id : undefined);
      setText("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  const agents = new Map(agent ? [[agent.id, agent]] : []);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" aria-label="社員スレッド">
        <header className="drawer-head">
          {agent && <Avatar name={agent.name} color={agent.avatar_color} size={40} />}
          <div className="grow">
            <div className="agent-name">{agent?.name}</div>
            <div className="muted small">{agent?.title}</div>
          </div>
          {agent && <StatusBadge agent={agent} />}
          <button type="button" className="btn" onClick={onClose} aria-label="閉じる">✕</button>
        </header>

        <section className="drawer-tasks">
          <div className="drawer-section-title">
            担当中のタスク（{openTasks.length}）
            {agent && <Link to={`/staff/${agent.id}`} onClick={onClose} className="small push-right">社員の詳細</Link>}
          </div>
          {openTasks.length === 0 && <p className="muted small">担当中のタスクはありません。</p>}
          {openTasks.map((t) => (
            <Link key={t.id} to={`/projects/${t.project_id}?task=${t.id}`} className="drawer-task" onClick={onClose}>
              <span className={`badge task-${t.status}`}>{TASK_STATUS[t.status]}</span>
              <span className="grow">{t.title}</span>
              <span className="muted small">{t.projectName}</span>
            </Link>
          ))}
          {doneTasks.length > 0 && (
            <details>
              <summary className="muted small">完了したタスク（{doneTasks.length}）</summary>
              {doneTasks.map((t) => (
                <Link key={t.id} to={`/projects/${t.project_id}?task=${t.id}`} className="drawer-task" onClick={onClose}>
                  <span className="badge task-done">完了</span>
                  <span className="grow">{t.title}</span>
                  <span className="muted small">{t.projectName}</span>
                </Link>
              ))}
            </details>
          )}
        </section>

        <MessageList messages={messages} agents={agents} pending={awaitingReply} />

        <form className="composer" onSubmit={send}>
          {error && <p className="status bad small">{error}</p>}
          {question && (
            <label className="toggle small">
              <input type="checkbox" checked={asAnswer} onChange={(e) => setAsAnswer(e.target.checked)} />
              いちばん新しい質問への回答として送る
            </label>
          )}
          <textarea
            rows={3}
            autoFocus={Boolean(draft)}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(e);
            }}
            placeholder={agent?.status === "working"
              ? "作業中の社員への指示は、次のステップで作業に反映されます"
              : "進捗を聞く、方向を修正する…（Ctrl+Enterで送信）"}
            disabled={!agent?.active}
          />
          <div className="form-actions">
            <button type="submit" className="btn primary" disabled={sending || !text.trim() || !agent?.active}>送信</button>
            {agent && !agent.active && <span className="muted small">休暇中の社員には送れません（復帰させると話せます）</span>}
          </div>
        </form>
      </aside>
    </>
  );
}
