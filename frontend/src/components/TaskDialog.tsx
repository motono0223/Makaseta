import { FormEvent, useEffect, useRef, useState } from "react";
import { Priority, ProjectMember, Task, TaskInput, TaskStatus } from "../api";
import { PRIORITY, TASK_COLUMNS, TASK_STATUS } from "../labels";
import TaskWorkPanel from "./TaskWorkPanel";

type Props = {
  task: Task | null; // null = new task
  members: ProjectMember[];
  onSave: (input: TaskInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
  onChanged?: () => void;
};

const EMPTY: TaskInput = {
  title: "",
  instructions: "",
  expected_output: "",
  priority: "normal",
  due_date: null,
  assignee_id: null,
  reviewer_id: null,
};

export default function TaskDialog({ task, members, onSave, onDelete, onClose, onChanged }: Props) {
  const [values, setValues] = useState<TaskInput>(task ? { ...task } : EMPTY);
  const [tab, setTab] = useState<"work" | "edit">(task && task.status !== "backlog" ? "work" : "edit");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const set = <K extends keyof TaskInput>(key: K, v: TaskInput[K]) => setValues((s) => ({ ...s, [key]: v }));
  const agentOption = (id: string) => (id ? Number(id) : null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSave(values);
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }

  async function remove() {
    if (!onDelete || !window.confirm("このタスクを削除しますか？")) return;
    try {
      await onDelete();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <dialog ref={dialog} className="dialog wide" onClose={onClose} onCancel={onClose}>
      {task && (
        <div className="dialog-head">
          <div>
            <h2>{task.title}</h2>
            <span className={`badge task-${task.status}`}>{TASK_STATUS[task.status]}</span>
          </div>
          <button type="button" className="btn" onClick={() => dialog.current?.close()} aria-label="閉じる">閉じる</button>
        </div>
      )}
      {task && (
        <nav className="tabs">
          <button type="button" className={tab === "work" ? "active" : ""} onClick={() => setTab("work")}>作業</button>
          <button type="button" className={tab === "edit" ? "active" : ""} onClick={() => setTab("edit")}>内容</button>
        </nav>
      )}
      {task && tab === "work" && <TaskWorkPanel task={task} onChanged={() => onChanged?.()} />}
      <form className="form" onSubmit={submit} hidden={!!task && tab !== "edit"}>
        {!task && <h2>タスクを追加</h2>}
        <div className="field">
          <label htmlFor="task-title">タイトル</label>
          <input id="task-title" value={values.title} maxLength={200} required autoFocus
            onChange={(e) => set("title", e.target.value)} placeholder="例: 現行規程の調査" />
        </div>
        <div className="field">
          <label htmlFor="task-instructions">指示</label>
          <textarea id="task-instructions" rows={5} value={values.instructions}
            onChange={(e) => set("instructions", e.target.value)} placeholder="何を、どこまでやってほしいか" />
        </div>
        <div className="field">
          <label htmlFor="task-output">期待する成果物</label>
          <input id="task-output" value={values.expected_output} onChange={(e) => set("expected_output", e.target.value)}
            placeholder="例: 要点をまとめたMarkdownのメモ" />
        </div>
        <div className="form-row">
          <div className="field grow">
            <label htmlFor="task-assignee">担当</label>
            <select id="task-assignee" value={values.assignee_id ?? ""} onChange={(e) => set("assignee_id", agentOption(e.target.value))}>
              <option value="">未割当</option>
              {members.map((m) => (
                <option key={m.agent.id} value={m.agent.id}>{m.agent.name}（{m.role.name}）</option>
              ))}
            </select>
          </div>
          <div className="field grow">
            <label htmlFor="task-reviewer">レビュー担当</label>
            <select id="task-reviewer" value={values.reviewer_id ?? ""} onChange={(e) => set("reviewer_id", agentOption(e.target.value))}>
              <option value="">なし（オフィス長が確認）</option>
              {members.map((m) => (
                <option key={m.agent.id} value={m.agent.id}>{m.agent.name}（{m.role.name}）</option>
              ))}
            </select>
          </div>
        </div>
        <div className="form-row">
          <div className="field">
            <label htmlFor="task-priority">優先度</label>
            <select id="task-priority" value={values.priority} onChange={(e) => set("priority", e.target.value as Priority)}>
              {(Object.keys(PRIORITY) as Priority[]).map((p) => (
                <option key={p} value={p}>{PRIORITY[p]}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="task-due">期限</label>
            <input id="task-due" type="date" value={values.due_date ?? ""} onChange={(e) => set("due_date", e.target.value || null)} />
          </div>
          {task && (
            <div className="field">
              <label htmlFor="task-status">状態</label>
              <select id="task-status" value={values.status ?? task.status}
                onChange={(e) => set("status", e.target.value as TaskStatus)}>
                {TASK_COLUMNS.map((c) => (
                  <option key={c.status} value={c.status}>{c.label}</option>
                ))}
              </select>
            </div>
          )}
        </div>
        {error && <p className="status bad">{error}</p>}
        <div className="form-actions">
          <button type="submit" className="btn primary" disabled={saving}>{saving ? "保存中…" : "保存する"}</button>
          <button type="button" className="btn" onClick={() => dialog.current?.close()}>キャンセル</button>
          {onDelete && (
            <button type="button" className="btn danger push-right" onClick={remove}>削除</button>
          )}
        </div>
      </form>
    </dialog>
  );
}
