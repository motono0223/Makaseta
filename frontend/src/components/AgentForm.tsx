import { FormEvent, useEffect, useState } from "react";
import { AgentInput, ModelProfile, Skill, api } from "../api";
import Avatar, { AVATAR_COLORS } from "./Avatar";

type Props = {
  initial: AgentInput;
  submitLabel: string;
  onSubmit: (values: AgentInput) => Promise<void>;
  onCancel?: () => void;
};

export default function AgentForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
  const [values, setValues] = useState<AgentInput>(initial);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setValues(initial), [initial]);

  useEffect(() => {
    api.skills().then(setSkills).catch((e: Error) => setError(e.message));
    api
      .modelProfiles()
      .then((all) => setProfiles(all.filter((p) => p.kind === "chat")))
      .catch((e: Error) => setError(e.message));
  }, []);

  const set = <K extends keyof AgentInput>(key: K, value: AgentInput[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  const toggleSkill = (id: number) =>
    set(
      "skill_ids",
      values.skill_ids.includes(id) ? values.skill_ids.filter((s) => s !== id) : [...values.skill_ids, id],
    );

  const selectedProfile = profiles.find((p) => p.name === values.model_profile);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit(values);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="form-row avatar-row">
        <Avatar name={values.name || "?"} color={values.avatar_color} size={56} />
        <div className="field grow">
          <label htmlFor="agent-name">名前</label>
          <input
            id="agent-name"
            value={values.name}
            maxLength={40}
            required
            onChange={(e) => set("name", e.target.value)}
            placeholder="例: 佐藤"
          />
        </div>
        <div className="field grow">
          <label htmlFor="agent-title">役職</label>
          <input
            id="agent-title"
            value={values.title}
            maxLength={40}
            onChange={(e) => set("title", e.target.value)}
            placeholder="例: リサーチャー"
          />
        </div>
      </div>

      <div className="field">
        <span className="label">アイコンの色</span>
        <div className="color-picker">
          {AVATAR_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              className={`color-swatch avatar-${c}${values.avatar_color === c ? " selected" : ""}`}
              aria-label={`色 ${c}`}
              aria-pressed={values.avatar_color === c}
              onClick={() => set("avatar_color", c)}
            />
          ))}
        </div>
      </div>

      <div className="field">
        <label htmlFor="agent-personality">性格・口調</label>
        <textarea
          id="agent-personality"
          rows={2}
          value={values.personality}
          onChange={(e) => set("personality", e.target.value)}
          placeholder="例: 慎重で率直。結論から話す。"
        />
      </div>

      <div className="field">
        <label htmlFor="agent-instructions">行動指針</label>
        <textarea
          id="agent-instructions"
          rows={4}
          value={values.instructions}
          onChange={(e) => set("instructions", e.target.value)}
          placeholder="この社員が仕事を進めるときに守ること"
        />
      </div>

      <div className="field">
        <label htmlFor="agent-model">使用モデル</label>
        <select id="agent-model" value={values.model_profile} onChange={(e) => set("model_profile", e.target.value)}>
          {profiles.map((p) => (
            <option key={p.name} value={p.name}>
              {p.label}（{p.name}）{p.available ? "" : " ※未設定"}
            </option>
          ))}
        </select>
        {selectedProfile && !selectedProfile.available && (
          <p className="hint warn">このモデルはまだ使えません: {selectedProfile.reason}</p>
        )}
      </div>

      <div className="field">
        <span className="label">スキル</span>
        <div className="skill-list">
          {skills.map((s) => (
            <label key={s.id} className="skill-option">
              <input type="checkbox" checked={values.skill_ids.includes(s.id)} onChange={() => toggleSkill(s.id)} />
              <span>
                <strong>{s.name}</strong>
                <span className="muted small"> {s.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      {error && <p className="status bad">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn primary" disabled={saving}>
          {saving ? "保存中…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            キャンセル
          </button>
        )}
      </div>
    </form>
  );
}
