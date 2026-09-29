export function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("ja-JP", { dateStyle: "short", timeStyle: "short" });
}

/** Build a router path for a 資料室 folder, encoding each segment. */
export function libraryPath(room: string, path = ""): string {
  const segments = [room, ...path.split("/").filter(Boolean)].map(encodeURIComponent);
  return `/library/${segments.join("/")}`;
}
