import { useCallback, useEffect, useRef, useState } from "react";
import { Run, Task, TaskWork, api } from "../api";
import { formatDate } from "../format";
import { usePolling } from "../usePolling";
import Markdown from "./Markdown";

const RUN_STATUS: Record<Run["status"], string> = {
  queued: "順番待ち",
  running: "作業中",
  waiting: "質問待ち",
  succeeded: "完了",
  failed: "エラー",
  cancelled: "中止",
  interrupted: "中断",
};

const STEP_LABEL: Record<string, string> = {
  search_documents: "資料を検索",
  list_documents: "フォルダを確認",
  read_document: "文書を読む",
  submit_deliverable: "成果物を提出",
  ask_manager: "オフィス長に質問",
  finish: "完了を報告",
};

type Props = { task: Task; onChanged: () => void };

/** What the assignee is doing on a task, and the office head's actions: answer, review, retry, stop. */
export default function TaskWorkPanel({ task, onChanged }: Props) {
  const [data, setData] = useState<TaskWork | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.taskWork(task.id).then(setData).catch((e: Error) => setError(e.message));
  }, [task.id]);

  const latest = data?.runs[0];
  const live = latest?.status === "queued" || latest?.status === "running";
  usePolling(load, live ? 2000 : 6000);

  // When the agent stops (finished, asked, failed), refresh the board so the card moves right away.
  const wasLive = useRef(false);
  useEffect(() => {
    if (wasLive.current && !live) onChanged();
    wasLive.current = live;
  }, [live, onChanged]);

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

  if (!data) return <p className="muted">読み込み中…</p>;
  const drafts = data.deliverables.filter((d) => d.status === "draft");
  const failed = latest && (latest.status === "failed" || latest.status === "interrupted" || latest.status === "cancelled");

  return (
    <div className="work-panel">
      {error && <p className="status bad">{error}</p>}

      {data.question && task.status === "waiting" && (
        <div className="callout question">
          <div className="callout-title">社員から質問が来ています</div>
          <p className="pre-line">{data.question.body}</p>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="回答を入力" />
          <div className="form-actions">
            <button type="button" className="btn primary" disabled={busy || !text.trim()}
              onClick={() => act(() => api.answerTask(task.id, text))}>
              回答して作業を再開
            </button>
          </div>
        </div>
      )}

      {task.status === "review" && (
        <div className="callout review">
          <div className="callout-title">成果物の確認をお願いします</div>
          {data.report && <Markdown>{data.report.body}</Markdown>}
          {drafts.length === 0 && <p className="muted small">提出された成果物はありません（報告のみ）。</p>}
          {drafts.map((d) => (
            <details key={d.id} open>
              <summary>
                📄 {d.room} / {d.path} <span className="muted small">（承認すると資料室に保存されます）</span>
              </summary>
              {d.path.toLowerCase().endsWith(".md") ? (
                <div className="file-content rendered"><Markdown>{d.content}</Markdown></div>
              ) : (
                <pre className="file-content">{d.content}</pre>
              )}
            </details>
          ))}
          <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="差し戻す場合は、直してほしい点を書いてください" />
          <div className="form-actions">
            <button type="button" className="btn primary" disabled={busy} onClick={() => act(() => api.approveTask(task.id))}>
              承認して完了にする
            </button>
            <button type="button" className="btn" disabled={busy || !text.trim()}
              onClick={() => act(() => api.rejectTask(task.id, text))}>
              差し戻す
            </button>
          </div>
        </div>
      )}

      {failed && task.status !== "done" && (
        <div className="callout failed">
          <div className="callout-title">作業が止まっています（{RUN_STATUS[latest.status]}）</div>
          {latest.error && <p className="pre-line">{latest.error}</p>}
          <div className="form-actions">
            <button type="button" className="btn primary" disabled={busy} onClick={() => act(() => api.retryTask(task.id))}>
              続きから再実行
            </button>
          </div>
        </div>
      )}

      {live && (
        <div className="form-actions">
          <span className="status ok">● {RUN_STATUS[latest.status]}（自動で更新します）</span>
          <button type="button" className="btn danger push-right" disabled={busy}
            onClick={() => window.confirm("作業を止めてバックログに戻しますか？") && act(() => api.cancelTask(task.id))}>
            止める
          </button>
        </div>
      )}

      {data.runs.length === 0 && (
        <p className="muted">まだ作業していません。担当者を決めてカードを「作業中」に移すと、社員が作業を始めます。</p>
      )}

      {data.runs.map((run, index) => (
        <details key={run.id} className="run" open={index === 0}>
          <summary>
            作業 #{run.id} · {RUN_STATUS[run.status]} · {run.steps}ステップ · ${Number(run.cost_usd).toFixed(4)}
            <span className="muted small"> {formatDate(run.started_at ?? run.created_at)}</span>
          </summary>
          <ol className="run-log">
            {run.log.map((step) => (
              <li key={step.id} className={`step step-${step.kind}`}>
                {step.kind === "tool_call" && <span className="step-label">🔧 {STEP_LABEL[step.name] ?? step.name}</span>}
                {step.kind === "tool_result" && <span className="step-label">↳ 結果</span>}
                {step.kind === "error" && <span className="step-label">⚠ エラー</span>}
                {step.kind === "info" && <span className="step-label">ℹ</span>}
                {step.kind === "text" ? (
                  <Markdown>{step.content}</Markdown>
                ) : (
                  <span className="step-content">{step.content}</span>
                )}
              </li>
            ))}
          </ol>
        </details>
      ))}
    </div>
  );
}
