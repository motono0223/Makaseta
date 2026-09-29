import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { InboxItem, api } from "../api";
import { useThread } from "../components/ThreadDrawer";
import { formatDate } from "../format";
import { usePolling } from "../usePolling";

const KIND: Record<InboxItem["kind"], { label: string; action: string }> = {
  question: { label: "質問", action: "回答する" },
  review: { label: "レビュー待ち", action: "確認する" },
  failed: { label: "エラー", action: "対応する" },
  plan: { label: "計画の提案", action: "計画を確認する" },
};

export default function Inbox() {
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const openThread = useThread();
  const load = useCallback(() => {
    api.inbox().then(setItems).catch((e: Error) => setError(e.message));
  }, []);
  usePolling(load, 5000);

  return (
    <>
      <h1>受信箱</h1>
      <p className="lead">社員からの質問、レビュー待ちの成果物、止まった作業がここに集まります。</p>
      {error && <p className="status bad">{error}</p>}
      {items && items.length === 0 && (
        <section className="card empty">
          <p>対応が必要なことはありません。</p>
        </section>
      )}
      <div className="inbox">
        {items?.map((item) => (
          <section key={`${item.kind}-${item.task_id ?? `p${item.plan_id}`}`} className={`card inbox-item inbox-${item.kind}`}>
            <div className="inbox-head">
              <span className={`badge inbox-badge-${item.kind}`}>{KIND[item.kind].label}</span>
              <strong className="grow">{item.task_title}</strong>
              <span className="muted small">{formatDate(item.created_at)}</span>
            </div>
            <div className="muted small">
              {item.project_name}
              {item.agent_name && (
                <>
                  {" · "}
                  <button type="button" className="link-button small" onClick={() => item.agent_id && openThread(item.agent_id)}>
                    {item.agent_name}
                  </button>
                </>
              )}
            </div>
            {item.body && <p className="pre-line clamp">{item.body}</p>}
            <Link className="btn primary" to={item.task_id ? `/projects/${item.project_id}?task=${item.task_id}`
              : `/projects/${item.project_id}?tab=thread`}>
              {KIND[item.kind].action}
            </Link>
          </section>
        ))}
      </div>
    </>
  );
}
