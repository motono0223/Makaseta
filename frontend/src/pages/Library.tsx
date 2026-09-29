import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LibraryRoom, LibraryStatus, SearchHit, api } from "../api";
import SearchResults from "../components/SearchResults";
import { formatDate, formatSize, libraryPath } from "../format";

export default function Library() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const [rooms, setRooms] = useState<LibraryRoom[] | null>(null);
  const [status, setStatus] = useState<LibraryStatus | null>(null);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searchText, setSearchText] = useState(query);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.rooms().then(setRooms).catch((e: Error) => setError(e.message));
    api.libraryStatus().then(setStatus).catch(() => undefined);
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    setSearchText(query);
    if (!query) {
      setHits(null);
      return;
    }
    api.search(query).then(setHits).catch((e: Error) => setError(e.message));
  }, [query]);

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    setParams(searchText.trim() ? { q: searchText.trim() } : {});
  }

  async function rescan() {
    setBusy(true);
    setError(null);
    try {
      await api.rescanLibrary();
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function createRoom(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createRoom(newName, newDescription);
      setCreating(false);
      setNewName("");
      setNewDescription("");
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>資料室</h1>
          <p className="lead">
            社員が読む資料と、社員が作った成果物の置き場です。
            {status && (
              <>
                {" "}
                ホストの <code>{status.host_path}</code> にフォルダやファイルをコピーしても追加できます。
              </>
            )}
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={rescan} disabled={busy}>
            {busy ? "読み込み中…" : "再読み込み"}
          </button>
          <button type="button" className="btn primary" onClick={() => setCreating((v) => !v)}>
            資料室を作る
          </button>
        </div>
      </div>

      {error && <p className="status bad">{error}</p>}

      {creating && (
        <section className="card">
          <form className="form" onSubmit={createRoom}>
            <div className="form-row">
              <div className="field grow">
                <label htmlFor="room-name">名前（フォルダ名になります）</label>
                <input id="room-name" value={newName} maxLength={80} required onChange={(e) => setNewName(e.target.value)}
                  placeholder="例: 社内規程" />
              </div>
              <div className="field grow">
                <label htmlFor="room-description">説明</label>
                <input id="room-description" value={newDescription} onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="例: 就業規則や各種規程" />
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn primary">作成する</button>
              <button type="button" className="btn" onClick={() => setCreating(false)}>キャンセル</button>
            </div>
          </form>
        </section>
      )}

      <form className="search-bar" onSubmit={submitSearch}>
        <input type="search" value={searchText} onChange={(e) => setSearchText(e.target.value)}
          placeholder="すべての資料室を検索（スペース区切りで複数語）" aria-label="資料を検索" />
        <button type="submit" className="btn">検索</button>
      </form>

      {hits && (
        <section className="card">
          <h2>検索結果（{hits.length}件）</h2>
          <SearchResults hits={hits} query={query} />
        </section>
      )}

      {rooms && rooms.length === 0 && (
        <section className="card empty">
          <p>まだ資料室がありません。「資料室を作る」か、ホストの資料室フォルダにフォルダを作ってください。</p>
        </section>
      )}

      <div className="agent-grid">
        {rooms?.map((r) => (
          <Link key={r.name} to={libraryPath(r.name)} className="agent-card">
            <div className="agent-card-head">
              <span className="room-icon" aria-hidden="true">📁</span>
              <div className="grow">
                <div className="agent-name">{r.name}</div>
                <div className="muted small">{r.description || "説明なし"}</div>
              </div>
            </div>
            <div className="muted small">
              {r.documents}件 · {formatSize(r.total_size)}
              {r.updated_at && ` · 更新 ${formatDate(r.updated_at)}`}
            </div>
          </Link>
        ))}
      </div>

      {status?.last_scan_at && (
        <p className="muted small footnote">
          最終スキャン {formatDate(status.last_scan_at)}（{status.documents}件を取り込み済み、30秒ごとに自動で確認）
        </p>
      )}
    </>
  );
}
