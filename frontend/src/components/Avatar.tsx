export const AVATAR_COLORS = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"];

export default function Avatar({ name, color, size = 40 }: { name: string; color: string; size?: number }) {
  const initial = Array.from(name.trim())[0] ?? "?";
  return (
    <span
      className={`avatar avatar-${color}`}
      style={{ width: size, height: size, fontSize: size * 0.45 }}
      aria-hidden="true"
    >
      {initial}
    </span>
  );
}
