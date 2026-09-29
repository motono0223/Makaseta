import { LibraryRoom, RoomLink } from "../api";

type Props = { rooms: LibraryRoom[]; value: RoomLink[]; onChange: (links: RoomLink[]) => void };

/** Choose which 資料室 the project's agents may read, and which they may also write to. */
export default function RoomsEditor({ rooms, value, onChange }: Props) {
  const unused = rooms.filter((r) => !value.some((l) => l.room === r.name));
  const setAccess = (room: string, access: RoomLink["access"]) =>
    onChange(value.map((l) => (l.room === room ? { ...l, access } : l)));

  return (
    <div className="members-editor">
      {value.length === 0 && <p className="muted small">リンクした資料室だけを、このプロジェクトの社員が読めます。</p>}
      {value.map((l) => (
        <div key={l.room} className="member-row">
          <span className="room-icon small-icon" aria-hidden="true">📁</span>
          <div className="grow">
            <div className="agent-name">{l.room}</div>
            {l.exists === false && <div className="status bad small">フォルダが見つかりません</div>}
          </div>
          <select value={l.access} onChange={(e) => setAccess(l.room, e.target.value as RoomLink["access"])}
            aria-label={`${l.room}の権限`}>
            <option value="read">読み取りのみ</option>
            <option value="write">読み書き（成果物を保存）</option>
          </select>
          <button type="button" className="link-button danger small" onClick={() => onChange(value.filter((x) => x.room !== l.room))}>
            外す
          </button>
        </div>
      ))}
      {unused.length > 0 && (
        <select className="add-member" value="" aria-label="資料室をリンク"
          onChange={(e) => e.target.value && onChange([...value, { room: e.target.value, access: "read" }])}>
          <option value="">＋ 資料室をリンク…</option>
          {unused.map((r) => (
            <option key={r.name} value={r.name}>{r.name}</option>
          ))}
        </select>
      )}
      {rooms.length === 0 && <p className="hint">資料室がまだありません。資料室の画面で作れます。</p>}
    </div>
  );
}
