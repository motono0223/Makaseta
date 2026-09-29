import { Link } from "react-router-dom";
import { SearchHit } from "../api";
import { formatSize, libraryPath } from "../format";

export default function SearchResults({ hits, query }: { hits: SearchHit[]; query: string }) {
  if (hits.length === 0) return <p className="muted">「{query}」に一致する資料はありません。</p>;
  return (
    <ul className="search-results">
      {hits.map((h) => {
        const folder = h.path.includes("/") ? h.path.slice(0, h.path.lastIndexOf("/")) : "";
        return (
          <li key={`${h.room}/${h.path}`}>
            <Link to={`${libraryPath(h.room, folder)}?${new URLSearchParams({ file: h.path })}`}>
              {h.room} / {h.path}
            </Link>
            <span className="muted small"> {formatSize(h.size)}</span>
            <p className="snippet">{h.snippet}</p>
          </li>
        );
      })}
    </ul>
  );
}
