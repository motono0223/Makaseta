import { FormEvent, useCallback, useEffect, useState } from "react";
import { AgentNote, AgentStats, api } from "../api";
import { formatDate } from "../format";

/** An agent's track record and 業務メモ: what it has learned and carries into its next work. */
export default function AgentGrowth({ agentId }: { agentId: number }) {
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [notes, setNotes] = useState<AgentNote[]>([]);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<{ id: number; body: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.agentStats(agentId).then(setStats).catch(() => undefined);
    api.notes(agentId).then(setNotes).catch((e: Error) => setError(e.message));
  }, [agentId]);
  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    run(async () => {
      await api.addNote(agentId, draft);
      setDraft("");
    });
  }

  return (
    <>
      {stats && (
        <div className="stat-row">
          <div className="stat">
            <span className="stat-value">{stats.tasks_done}</span>
            <span className="stat-label">完了したタスク（担当中 {stats.tasks_open}）</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {stats.first_pass_rate === null ? "–" : `${Math.round(stats.first_pass_rate * 100)}%`}
            </span>
            <span className="stat-label">一発で承認された割合（差し戻し {stats.rejections}回）</span>
          </div>
          <div className="stat">
            <span className="stat-value">{stats.projects}</span>
            <span className="stat-label">参加したプロジェクト</span>
          </div>
          <div className="stat">
            <span className="stat-value">${stats.cost_usd.toFixed(2)}</span>
            <span className="stat-label">これまでの利用料金</span>
          </div>
        </div>
      )}

      <section className="card">
        <h2>業務メモ（これまでに学んだこと）</h2>
        <p className="muted small">
          タスクが承認・差し戻しされるたびに、社員が振り返って学びを書き足します。社員は次の仕事でこのメモを読んでから取りかかります。
          間違っている内容は直すか消してください。
        </p>
        {error && <p className="status bad">{error}</p>}
        {notes.length === 0 && <p className="muted">まだありません。仕事をしてレビューを受けると増えていきます。</p>}
        <ul className="notes">
          {notes.map((n) => (
            <li key={n.id}>
              {editing?.id === n.id ? (
                <form className="inline-form" onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    await api.editNote(n.id, editing.body);
                    setEditing(null);
                  });
                }}>
                  <input value={editing.body} onChange={(e) => setEditing({ id: n.id, body: e.target.value })} autoFocus
                    aria-label="業務メモ" maxLength={500} />
                  <button type="submit" className="btn primary">保存</button>
                  <button type="button" className="btn" onClick={() => setEditing(null)}>キャンセル</button>
                </form>
              ) : (
                <>
                  <span className="note-body">{n.body}</span>
                  <span className="muted small note-meta">
                    {n.source === "manager" ? "オフィス長" : n.task_title ? `「${n.task_title}」から` : "振り返り"} · {formatDate(n.updated_at)}
                    {" "}
                    <button type="button" className="link-button small" onClick={() => setEditing({ id: n.id, body: n.body })}>直す</button>
                    {" "}
                    <button type="button" className="link-button danger small"
                      onClick={() => window.confirm("この業務メモを消しますか？") && run(() => api.deleteNote(n.id))}>消す</button>
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
        <form className="inline-form" onSubmit={add}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={500}
            placeholder="オフィス長から伝えておきたいこと（例: 報告は結論から3行で）" aria-label="業務メモを追加" />
          <button type="submit" className="btn" disabled={!draft.trim()}>追加</button>
        </form>
      </section>
    </>
  );
}
