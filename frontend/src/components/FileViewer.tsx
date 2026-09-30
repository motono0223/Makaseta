import { useEffect, useState } from "react";
import { Agent, FileVersion, Project, TextView, api, libraryUrl } from "../api";
import { copyText } from "../clipboard";
import { useThread } from "./ThreadDrawer";
import { formatDate, formatSize } from "../format";
import Markdown from "./Markdown";

type Props = { room: string; path: string; onClose: () => void; onSaved: () => void };

export default function FileViewer({ room, path, onClose, onSaved }: Props) {
  const [view, setView] = useState<TextView | null>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [versions, setVersions] = useState<FileVersion[] | null>(null);
  const [preview, setPreview] = useState<{ version: string; content: string } | null>(null);
  const [talk, setTalk] = useState<{ agents: Agent[]; projects: Project[] } | null>(null);
  const openThread = useThread();
  const fullPath = `${room}/${path}`;

  useEffect(() => {
    setView(null);
    setVersions(null);
    setPreview(null);
    setEditing(false);
    setError(null);
    setNotice(null);
    api
      .viewText(room, path)
      .then((v) => {
        setView(v);
        setDraft(v.content);
      })
      .catch((e: Error) => setError(e.message));
  }, [room, path]);

  async function save() {
    setError(null);
    try {
      await api.saveText(room, path, draft);
      setView((v) => v && { ...v, content: draft });
      setEditing(false);
      setNotice("保存しました");
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const name = path.split("/").pop();

  return (
    <section className="card viewer">
      <div className="viewer-head">
        <h2>{name}</h2>
        <div className="header-actions">
          {view?.editable && !editing && (
            <button type="button" className="btn" onClick={() => setEditing(true)}>編集</button>
          )}
          <a className="btn" href={libraryUrl.download(room, path)}>ダウンロード</a>
          <button type="button" className="btn" onClick={async () =>
            setNotice(await copyText(fullPath) ? `パスをコピーしました: ${fullPath}` : "コピーできませんでした")}>
            📋 パスをコピー
          </button>
          <button type="button" className="btn primary" onClick={() => talk ? setTalk(null)
            : Promise.all([api.agents(), api.projects()]).then(([agents, projects]) => setTalk({ agents, projects }))
              .catch((e: Error) => setError(e.message))}>
            💬 社員と話す
          </button>
          <button type="button" className="btn" onClick={() => versions ? setVersions(null)
            : api.versions(room, path).then(setVersions).catch((e: Error) => setError(e.message))}>
            過去の版
          </button>
          <button type="button" className="btn" onClick={onClose} aria-label="閉じる">閉じる</button>
        </div>
      </div>
      {notice && <p className="status ok">{notice}</p>}
      {talk && (
        <TalkPicker room={room} agents={talk.agents} projects={talk.projects}
          onPick={(agentId) => {
            setTalk(null);
            openThread(agentId, `「${fullPath}」について: `);
          }} />
      )}
      {versions && (
        <div className="versions">
          {versions.length === 0 && <p className="muted small">過去の版はありません（上書きされると、ここに残ります）。</p>}
          {versions.map((v) => (
            <div key={v.version} className="member-row small">
              <span className="grow">{formatDate(v.saved_at)} に退避した版 <span className="muted">{formatSize(v.size)}</span></span>
              <button type="button" className="link-button small" onClick={() => api.versionText(room, path, v.version)
                .then((t) => setPreview({ version: v.version, content: t.content || "（この形式は表示できません）" }))
                .catch((e: Error) => setError(e.message))}>中身を見る</button>
              <button type="button" className="btn small-btn" onClick={async () => {
                if (!window.confirm("この版に戻しますか？今の内容も過去の版として残ります。")) return;
                try {
                  await api.restoreVersion(room, path, v.version);
                  setNotice("この版に戻しました");
                  setVersions(null);
                  setPreview(null);
                  const fresh = await api.viewText(room, path);
                  setView(fresh);
                  setDraft(fresh.content);
                  onSaved();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}>この版に戻す</button>
            </div>
          ))}
          {preview && (
            <>
              <div className="small"><strong>選んだ版の中身</strong>（今の内容はこの下に表示されています）</div>
              <pre className="file-content">{preview.content}</pre>
            </>
          )}
        </div>
      )}
      {error && <p className="status bad">{error}</p>}
      {view?.source === "extracted" && (
        <p className="muted small">元のファイルから取り出したテキストを表示しています（社員が読むのはこの内容です）。</p>
      )}
      {view?.extract_error && <p className="status bad small">テキストを取り出せませんでした: {view.extract_error}</p>}
      {view?.source === "none" && <p className="muted">この形式は表示できません。ダウンロードして開いてください。</p>}
      {view && view.source !== "none" && !editing && (
        /\.(md|markdown)$/i.test(path) && view.content ? (
          <div className="file-content rendered"><Markdown>{view.content}</Markdown></div>
        ) : (
          <pre className="file-content">{view.content || "（空のファイル）"}</pre>
        )
      )}
      {editing && (
        <>
          <textarea className="file-editor" value={draft} onChange={(e) => setDraft(e.target.value)} rows={18} />
          <div className="form-actions">
            <button type="button" className="btn primary" onClick={save}>保存する</button>
            <button type="button" className="btn" onClick={() => { setEditing(false); setDraft(view?.content ?? ""); }}>
              キャンセル
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/** Choose who to ask about a file; agents on a project that links the room can read it in conversation. */
function TalkPicker({ room, agents, projects, onPick }: {
  room: string;
  agents: Agent[];
  projects: Project[];
  onPick: (agentId: number) => void;
}) {
  const linking = projects.filter((p) => p.rooms.some((r) => r.room === room));
  const readers = new Set(linking.flatMap((p) => p.members.map((m) => m.agent.id)));
  const sorted = [...agents].sort((a, b) => Number(readers.has(b.id)) - Number(readers.has(a.id)));
  return (
    <div className="talk-picker">
      <div className="small"><strong>このファイルについて誰と話しますか？</strong></div>
      {linking.length === 0 && (
        <p className="hint warn">この資料室は、どのプロジェクトにもリンクされていません。社員が読めるように、プロジェクトの設定でリンクしてください。</p>
      )}
      <div className="name-ideas">
        {sorted.map((a) => (
          <button key={a.id} type="button" className="name-idea" onClick={() => onPick(a.id)}>
            <strong>{a.name}</strong>
            <span className="muted small">
              {a.title}{readers.has(a.id) ? "" : " · この資料室を読めません"}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
