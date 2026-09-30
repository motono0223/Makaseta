import { useCallback, useEffect, useRef, useState } from "react";
import { Plan, ProjectMember, Run, Task, TaskWork, api } from "../api";
import { TASK_STATUS } from "../labels";
import { PlanCard } from "./ProjectThread";
import { formatDate, formatSize } from "../format";
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
  read_skill: "スキルの手順書を読む",
  read_skill_file: "スキルのファイルを読む",
  run_command: "コマンドを実行",
  list_workspace: "作業フォルダを確認",
  read_workspace_file: "作業ファイルを読む",
  write_workspace_file: "作業ファイルを書く",
  copy_to_workspace: "資料を作業フォルダへコピー",
  submit_file: "ファイルを提出",
  ask_manager: "オフィス長に質問",
  finish: "完了を報告",
  ask_colleague: "同僚に相談",
  web_search: "Webを検索",
  web_fetch: "Webページを読む",
  read_deliverables: "成果物を読む",
  approve_work: "レビュー: 問題なし",
  request_changes: "レビュー: 修正を依頼",
};

type Props = { task: Task; tasks: Task[]; members: ProjectMember[]; onChanged: () => void };

/** What the assignee is doing on a task, and the office head's actions: answer, review, retry, stop, split. */
export default function TaskWorkPanel({ task, tasks, members, onChanged }: Props) {
  const [data, setData] = useState<TaskWork | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.taskWork(task.id).then(setData).catch((e: Error) => setError(e.message));
    api.plans(task.project_id)
      .then((all) => setPlans(all.filter((p) => p.parent_task_id === task.id && (p.status === "drafting" || p.status === "proposed"))))
      .catch(() => undefined);
  }, [task.id, task.project_id]);

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
  const children = tasks.filter((t) => t.parent_id === task.id);
  const nameOf = (id: number | null) => members.find((m) => m.agent.id === id)?.agent.name ?? "未割当";
  const canSplit = task.status === "backlog" && children.length === 0 && !task.managing && plans.length === 0;
  const drafts = data.deliverables.filter((d) => d.status === "draft");
  const failed = latest && (latest.status === "failed" || latest.status === "interrupted" || latest.status === "cancelled");

  return (
    <div className="work-panel">
      {error && <p className="status bad">{error}</p>}

      {plans.map((plan) => (
        <PlanCard key={plan.id} plan={plan} busy={busy} onAct={act} />
      ))}

      {children.length > 0 && (
        <div className="subtasks">
          <div className="small"><strong>サブタスク（{children.filter((c) => c.status === "done").length}/{children.length} 完了）</strong></div>
          <ul className="task-list">
            {children.map((c) => (
              <li key={c.id}>
                <span className={`badge task-${c.status}`}>{TASK_STATUS[c.status]}</span> {c.title}
                <span className="muted small"> · {nameOf(c.assignee_id)}</span>
              </li>
            ))}
          </ul>
          {task.status === "in_progress" && children.some((c) => c.status !== "done") && (
            <p className="muted small">サブタスクが全部終わると、{nameOf(task.assignee_id)}さんが取りまとめて報告します。</p>
          )}
        </div>
      )}

      {canSplit && (
        <div className="form-actions">
          <button type="button" className="btn" disabled={busy} onClick={() => act(() => api.decomposeTask(task.id))}>
            🧭 マネージャーに分解させる
          </button>
          <span className="muted small">大きなタスクを、マネージャーがサブタスクに分けてメンバーに割り振ります</span>
        </div>
      )}

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
          {task.review_stage === "peer" && (
            <p className="small status ok">👀 レビュー担当の社員が確認中です。待たずにオフィス長が判断することもできます。</p>
          )}
          {data.report && <Markdown>{data.report.body}</Markdown>}
          {data.peer_review && task.review_stage !== "peer" && (
            <div className="peer-review">
              <div className="small"><strong>レビュー担当の所見</strong></div>
              <Markdown>{data.peer_review.body}</Markdown>
            </div>
          )}
          {drafts.length === 0 && <p className="muted small">提出された成果物はありません（報告のみ）。</p>}
          {drafts.map((d) => (
            <details key={d.id} open>
              <summary>
                📄 {d.room} / {d.path}{" "}
                {d.overwrites ? (
                  <span className="status bad small">⚠ 既存のファイルを上書きします（旧版は資料室の .makaseta/versions に残ります）</span>
                ) : (
                  <span className="muted small">（承認すると資料室に保存されます）</span>
                )}
              </summary>
              {d.file_size !== null ? (
                <p className="small">
                  📎 ファイル（{formatSize(d.file_size)}）{" "}
                  <a className="btn small-btn" href={`/api/deliverables/${d.id}/download`}>ダウンロードして確認</a>
                </p>
              ) : d.path.toLowerCase().endsWith(".md") ? (
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

      {data.runs.length === 0 && children.length === 0 && plans.length === 0 && (
        <p className="muted">
          {task.managing ? "マネージャーが割り振りを考えています。"
            : "まだ作業していません。担当者を決めてカードを「作業中」に移すと、社員が作業を始めます。"}
        </p>
      )}

      {data.runs.map((run, index) => (
        <details key={run.id} className="run" open={index === 0}>
          <summary>
            {run.kind === "review" ? "レビュー" : "作業"} #{run.id} · {RUN_STATUS[run.status]} · {run.steps}ステップ · ${Number(run.cost_usd).toFixed(4)}
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
