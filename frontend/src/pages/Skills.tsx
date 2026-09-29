import { FormEvent, useCallback, useEffect, useState } from "react";
import { SkillDetail, SkillPreview, api } from "../api";
import Markdown from "../components/Markdown";
import { formatSize } from "../format";

export default function Skills() {
  const [skills, setSkills] = useState<SkillDetail[] | null>(null);
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<SkillPreview | null>(null);
  const [replace, setReplace] = useState(false);
  const [open, setOpen] = useState<SkillDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    api.skillDetails().then(setSkills).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>, done?: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      if (done) setNotice(done);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function fetchPreview(e: FormEvent) {
    e.preventDefault();
    run(async () => {
      setPreview(await api.previewSkill(url));
      setReplace(false);
    });
  }

  const packages = skills?.filter((s) => s.source === "package") ?? [];
  const builtins = skills?.filter((s) => s.source !== "package") ?? [];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>スキル</h1>
          <p className="lead">
            社員に付けられる能力です。GitHubなどで公開されている Agent Skills（SKILL.md とスクリプトのフォルダ）を取り込めます。
            ホストの <code>./skills</code> にフォルダをコピーしても追加できます。
          </p>
        </div>
        <button type="button" className="btn" disabled={busy} onClick={() => run(async () => setSkills(await api.rescanSkills()), "フォルダを読み込み直しました")}>
          フォルダを再読み込み
        </button>
      </div>

      {notice && <p className="status ok">{notice}</p>}
      {error && <p className="status bad">{error}</p>}

      <section className="card">
        <h2>GitHubから取り込む</h2>
        <form className="search-bar compact" onSubmit={fetchPreview}>
          <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} required
            placeholder="https://github.com/anthropics/skills/tree/main/skills/pptx" aria-label="スキルのURL" />
          <button type="submit" className="btn primary" disabled={busy}>{busy && !preview ? "取得中…" : "内容を確認"}</button>
        </form>
        <p className="muted small">SKILL.md があるフォルダのURLを指定します。導入する前に中身を確認できます。</p>

        {preview && (
          <div className="callout review">
            <div className="callout-title">「{preview.name}」を導入しますか？</div>
            <p className="small">{preview.description}</p>
            {preview.license && <p className="small muted">ライセンス: {preview.license}</p>}
            <p className="small">
              ファイル {preview.files.length}件（うちスクリプト {preview.files.filter((f) => f.script).length}件）→
              <code>./skills/{preview.folder}</code>
            </p>
            <p className="status bad small">
              スキルのスクリプトは、社員がサンドボックスで実行します。信頼できる提供元のスキルだけを導入してください。
            </p>
            <details>
              <summary className="small">手順書（SKILL.md）を読む</summary>
              <div className="file-content rendered"><Markdown>{preview.body}</Markdown></div>
            </details>
            <details>
              <summary className="small">ファイル一覧</summary>
              <ul className="file-list small">
                {preview.files.map((f) => (
                  <li key={f.path}>{f.script ? "⚙ " : ""}{f.path} <span className="muted">{formatSize(f.size)}</span></li>
                ))}
              </ul>
            </details>
            {preview.exists && (
              <label className="toggle small">
                <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
                同じ名前のスキルがあります。置き換える
              </label>
            )}
            <div className="form-actions">
              <button type="button" className="btn primary" disabled={busy || (preview.exists && !replace)}
                onClick={() => run(async () => {
                  await api.installSkill(preview.stage_id, replace);
                  setPreview(null);
                  setUrl("");
                  load();
                }, `スキル「${preview.name}」を導入しました。社員名簿から社員に付けてください。`)}>
                導入する
              </button>
              <button type="button" className="btn" disabled={busy}
                onClick={() => run(async () => {
                  await api.discardSkill(preview.stage_id);
                  setPreview(null);
                })}>
                やめる
              </button>
            </div>
          </div>
        )}
      </section>

      <h2 className="section-title">スキルパッケージ（{packages.length}）</h2>
      {packages.length === 0 && <p className="muted">まだありません。</p>}
      <div className="agent-grid">
        {packages.map((s) => (
          <button key={s.id} type="button" className="agent-card skill-card" onClick={() => api.skillDetail(s.id).then(setOpen)}>
            <div className="agent-card-head">
              <span className="room-icon" aria-hidden="true">🧩</span>
              <div className="grow">
                <div className="agent-name">{s.name}</div>
                <div className="muted small">{s.folder}</div>
              </div>
              {!s.enabled && <span className="badge badge-error">無効</span>}
            </div>
            <div className="muted small clamp">{s.description}</div>
            <div className="muted small">{s.agents.length ? `使っている社員: ${s.agents.join("、")}` : "まだ誰にも付けていません"}</div>
          </button>
        ))}
      </div>

      <h2 className="section-title">組み込みスキル</h2>
      <div className="agent-grid">
        {builtins.map((s) => (
          <div key={s.id} className="agent-card static">
            <div className="agent-name">{s.name}</div>
            <div className="muted small">{s.description}</div>
            <div className="muted small">{s.agents.length ? `使っている社員: ${s.agents.join("、")}` : ""}</div>
          </div>
        ))}
      </div>

      {open && <SkillDialog skill={open} onClose={() => setOpen(null)} onDeleted={() => {
        setOpen(null);
        load();
      }} />}
    </>
  );
}

function SkillDialog({ skill, onClose, onDeleted }: { skill: SkillDetail; onClose: () => void; onDeleted: () => void }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <dialog className="dialog wide" open onClose={onClose}>
      <div className="dialog-head">
        <div>
          <h2>{skill.name}</h2>
          <span className="muted small">./skills/{skill.folder}</span>
        </div>
        <button type="button" className="btn" onClick={onClose}>閉じる</button>
      </div>
      <p className="small">{skill.description}</p>
      {skill.source_url && (
        <p className="small">取り込み元: <a href={skill.source_url} target="_blank" rel="noreferrer">{skill.source_url}</a></p>
      )}
      {skill.license && <p className="small muted">ライセンス: {skill.license}</p>}
      <details open>
        <summary className="small">手順書（SKILL.md）</summary>
        <div className="file-content rendered"><Markdown>{skill.body || "（読み込めませんでした）"}</Markdown></div>
      </details>
      <details>
        <summary className="small">ファイル一覧（{skill.files.length}）</summary>
        <ul className="file-list small">
          {skill.files.map((f) => (
            <li key={f.path}>{f.script ? "⚙ " : ""}{f.path} <span className="muted">{formatSize(f.size)}</span></li>
          ))}
        </ul>
      </details>
      {error && <p className="status bad">{error}</p>}
      <div className="form-actions spaced">
        <button type="button" className="btn danger" onClick={async () => {
          if (!window.confirm(`スキル「${skill.name}」を削除しますか？フォルダも削除され、社員からも外れます。`)) return;
          try {
            await api.deleteSkill(skill.id);
            onDeleted();
          } catch (e) {
            setError((e as Error).message);
          }
        }}>
          このスキルを削除
        </button>
      </div>
    </dialog>
  );
}
