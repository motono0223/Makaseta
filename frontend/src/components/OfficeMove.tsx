import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatDate, formatSize } from "../format";

type Export = { name: string; size: number; created_at: string };

/** Export the whole office to one zip, or replace this office with one exported elsewhere. */
export default function OfficeMove() {
  const [exports, setExports] = useState<Export[]>([]);
  const [includeWork, setIncludeWork] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.officeExports().then(setExports).catch(() => undefined);
  }, []);
  useEffect(load, [load]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
      load();
    }
  }

  function onImport(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!window.confirm(
      `「${file.name}」を取り込みますか？\n\nこのオフィスの社員・プロジェクト・資料室・スキルは、すべて取り込むファイルの内容に置き換わります。` +
      "取り込む前の状態は、自動でバックアップとして書き出されます。",
    )) return;
    run("import", async () => {
      const result = await api.importOffice(file);
      setNotice(`取り込みました（バックアップ: ${result.backup}）。画面を読み込み直します…`);
      window.setTimeout(() => window.location.reload(), 1500);
    });
  }

  return (
    <section className="card">
      <h2>オフィスの引っ越し</h2>
      <p className="muted small">
        社員（業務メモを含む）・プロジェクト・会話・資料室・スキルを1つのファイルに書き出し、別のPCの makaseta で取り込めます。
        <code>.env</code>（APIキーやパスワード）は含まれないので、引っ越し先で設定してください。
      </p>
      {notice && <p className="status ok">{notice}</p>}
      {error && <p className="status bad">{error}</p>}

      <div className="form-actions">
        <button type="button" className="btn primary" disabled={busy !== null}
          onClick={() => run("export", async () => {
            const result = await api.exportOffice(includeWork);
            setNotice(`書き出しました: ${result.name}（${formatSize(result.size)}）`);
          })}>
          {busy === "export" ? "書き出し中…" : "書き出す"}
        </button>
        <label className="toggle small">
          <input type="checkbox" checked={includeWork} onChange={(e) => setIncludeWork(e.target.checked)} />
          タスクの作業フォルダも含める
        </label>
      </div>

      {exports.length > 0 && (
        <table className="table spaced-table">
          <tbody>
            {exports.map((x) => (
              <tr key={x.name}>
                <td className="small">{x.name}</td>
                <td className="num muted small">{formatSize(x.size)}</td>
                <td className="muted small">{formatDate(x.created_at)}</td>
                <td className="num">
                  <a className="btn small-btn" href={`/api/office/exports/${encodeURIComponent(x.name)}`}>ダウンロード</a>{" "}
                  <button type="button" className="link-button danger small"
                    onClick={() => window.confirm(`${x.name} を削除しますか？`) && run("delete", () => api.deleteOfficeExport(x.name))}>
                    削除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="form-actions spaced">
        <button type="button" className="btn danger" disabled={busy !== null} onClick={() => fileInput.current?.click()}>
          {busy === "import" ? "取り込み中…" : "書き出したファイルを取り込む"}
        </button>
        <span className="muted small">このオフィスの内容は置き換わります（取り込む前に自動でバックアップします）</span>
        <input ref={fileInput} type="file" accept=".zip" hidden onChange={onImport} />
      </div>
    </section>
  );
}
