import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, LibraryEntry, LibraryRoom as LibraryRoomInfo, SearchHit, api } from "../api";
import FileViewer from "../components/FileViewer";
import SearchResults from "../components/SearchResults";
import { formatDate, formatSize, libraryPath } from "../format";

type Mode = null | "folder" | "note";

export default function LibraryRoom() {
  const params = useParams();
  const room = params.room ?? "";
  const folder = params["*"] ?? "";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const openFile = searchParams.get("file");
  const [entries, setEntries] = useState<LibraryEntry[] | null>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [newName, setNewName] = useState("");
  const [searchText, setSearchText] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.entries(room, folder).then(setEntries).catch((e: Error) => setError(e.message));
  }, [room, folder]);

  useEffect(() => {
    setEntries(null);
    setError(null);
    setNotice(null);
    setHits(null);
    load();
  }, [load]);

  const inFolder = (name: string) => (folder ? `${folder}/${name}` : name);
  const showFile = (path: string | null) => setSearchParams(path ? { file: path } : {});

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(done);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length === 0) return;
    await run(async () => {
      try {
        await api.upload(room, folder, files);
      } catch (err) {
        if (err instanceof ApiError && err.message.startsWith("同じ名前") && window.confirm(`${err.message}\n上書きしますか？`)) {
          await api.upload(room, folder, files, true);
          return;
        }
        throw err;
      }
    }, `${files.length}件のファイルを追加しました`);
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    if (mode === "folder") {
      await run(() => api.createFolder(room, inFolder(name)), `フォルダ「${name}」を作りました`);
    } else {
      const fileName = /\.(md|markdown|txt)$/i.test(name) ? name : `${name}.md`;
      await run(async () => {
        await api.createText(room, inFolder(fileName), `# ${name.replace(/\.(md|markdown|txt)$/i, "")}\n\n`);
        showFile(inFolder(fileName));
      }, `メモ「${fileName}」を作りました`);
    }
    setMode(null);
    setNewName("");
  }

  async function onDelete(entry: LibraryEntry) {
    if (!window.confirm(`「${entry.name}」を削除しますか？ホストのフォルダからも消えます。`)) return;
    await run(() => api.deleteEntry(room, entry.path), `「${entry.name}」を削除しました`);
    if (openFile === entry.path) showFile(null);
  }

  async function onDeleteRoom() {
    if (!window.confirm(`資料室「${room}」を削除しますか？（空の資料室だけ削除できます）`)) return;
    setError(null);
    try {
      await api.deleteRoom(room);
      navigate("/library");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    const text = searchText.trim();
    if (!text) {
      setHits(null);
      return;
    }
    api.search(text, room).then(setHits).catch((err: Error) => setError(err.message));
  }

  const crumbs = folder.split("/").filter(Boolean);

  return (
    <>
      <p className="breadcrumb">
        <Link to="/library">資料室</Link>
        {" / "}
        <Link to={libraryPath(room)}>{room}</Link>
        {crumbs.map((c, i) => (
          <span key={i}>
            {" / "}
            <Link to={libraryPath(room, crumbs.slice(0, i + 1).join("/"))}>{c}</Link>
          </span>
        ))}
      </p>
      <div className="page-header">
        <h1>{crumbs.at(-1) ?? room}</h1>
        <div className="header-actions">
          <button type="button" className="btn primary" onClick={() => fileInput.current?.click()} disabled={busy}>
            アップロード
          </button>
          <button type="button" className="btn" onClick={() => setMode(mode === "note" ? null : "note")}>新しいメモ</button>
          <button type="button" className="btn" onClick={() => setMode(mode === "folder" ? null : "folder")}>新しいフォルダ</button>
          <input ref={fileInput} type="file" multiple hidden onChange={onUpload} />
        </div>
      </div>

      {mode && (
        <form className="inline-form" onSubmit={onCreate}>
          <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={80}
            placeholder={mode === "folder" ? "フォルダ名" : "メモの名前（例: 議事録）"} aria-label="名前" />
          <button type="submit" className="btn primary">作成</button>
          <button type="button" className="btn" onClick={() => setMode(null)}>キャンセル</button>
        </form>
      )}

      {notice && <p className="status ok">{notice}</p>}
      {error && <p className="status bad">{error}</p>}

      {openFile && (
        <FileViewer room={room} path={openFile} onClose={() => showFile(null)} onSaved={load} />
      )}

      <section className="card">
        <form className="search-bar compact" onSubmit={onSearch}>
          <input type="search" value={searchText} onChange={(e) => setSearchText(e.target.value)}
            placeholder={`「${room}」の中を検索`} aria-label="この資料室を検索" />
          <button type="submit" className="btn">検索</button>
        </form>
        {hits && <SearchResults hits={hits} query={searchText} />}

        {entries && entries.length === 0 && <p className="muted">このフォルダは空です。</p>}
        {entries && entries.length > 0 && (
          <table className="table file-table">
            <thead>
              <tr>
                <th>名前</th>
                <th>サイズ</th>
                <th>更新</th>
                <th>取り込み</th>
                <th aria-label="操作" />
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.path} className={openFile === e.path ? "selected" : ""}>
                  <td>
                    {e.is_dir ? (
                      <Link to={libraryPath(room, e.path)}>📁 {e.name}</Link>
                    ) : (
                      <button type="button" className="link-button" onClick={() => showFile(e.path)}>
                        📄 {e.name}
                      </button>
                    )}
                  </td>
                  <td className="muted small">{formatSize(e.size)}</td>
                  <td className="muted small">{formatDate(e.modified_at)}</td>
                  <td className="small">
                    {e.is_dir ? "" : e.extract_error ? (
                      <span className="status bad" title={e.extract_error}>読めません</span>
                    ) : e.indexed ? (
                      e.text_chars > 0 ? <span className="status ok">済（{e.text_chars.toLocaleString()}字）</span>
                        : <span className="muted">本文なし</span>
                    ) : (
                      <span className="muted">待ち</span>
                    )}
                  </td>
                  <td>
                    <button type="button" className="link-button danger small" onClick={() => onDelete(e)}>削除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {!folder && <RoomSettings room={room} onError={setError} />}

      {!folder && (
        <p className="footnote">
          <button type="button" className="link-button danger small" onClick={onDeleteRoom}>この資料室を削除</button>
        </p>
      )}
    </>
  );
}

function RoomSettings({ room, onError }: { room: string; onError: (message: string) => void }) {
  const [settings, setSettings] = useState<LibraryRoomInfo | null>(null);
  const [description, setDescription] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.rooms().then((rooms) => {
      const found = rooms.find((r) => r.name === room) ?? null;
      setSettings(found);
      setDescription(found?.description ?? "");
    }).catch(() => undefined);
  }, [room]);

  async function save(changes: { description?: string; confidential?: boolean }) {
    setSaved(false);
    try {
      await api.updateRoom(room, changes);
      setSettings((s) => s && { ...s, ...changes });
      setSaved(true);
    } catch (e) {
      onError((e as Error).message);
    }
  }

  if (!settings) return null;
  return (
    <section className="card">
      <h2>この資料室の設定</h2>
      <div className="inline-form">
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="説明（例: 就業規則や各種規程）"
          aria-label="資料室の説明" maxLength={2000} />
        <button type="button" className="btn" onClick={() => save({ description })}>説明を保存</button>
      </div>
      <label className="toggle">
        <input type="checkbox" checked={settings.confidential} onChange={(e) => save({ confidential: e.target.checked })} />
        🔒 機密にする（許可したモデルを使う社員だけが読めます。既定では Bedrock のみ。.env の CONFIDENTIAL_PROVIDERS で変更）
      </label>
      {saved && <p className="status ok small">保存しました</p>}
    </section>
  );
}
