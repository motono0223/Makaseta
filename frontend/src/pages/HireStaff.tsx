import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AgentInput, AgentTemplate, ModelProfile, Skill, api } from "../api";
import AgentForm from "../components/AgentForm";
import Avatar from "../components/Avatar";

const BLANK = "blank";

export default function HireStaff() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.agentTemplates(), api.skills(), api.modelProfiles()])
      .then(([t, s, p]) => {
        setTemplates(t);
        setSkills(s);
        setProfiles(p);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const defaultProfile =
    profiles.find((p) => p.is_default && p.kind === "chat")?.name ?? profiles.find((p) => p.kind === "chat")?.name ?? "";

  const initial = useMemo<AgentInput | null>(() => {
    if (chosen === null) return null;
    const t = templates.find((x) => x.key === chosen);
    return {
      name: "",
      title: t?.title ?? "",
      avatar_color: t?.avatar_color ?? "c1",
      personality: t?.personality ?? "",
      instructions: t?.instructions ?? "",
      model_profile: defaultProfile,
      skill_ids: skills.filter((s) => s.key && t?.skill_keys.includes(s.key)).map((s) => s.id),
      template_key: t?.key ?? null,
    };
  }, [chosen, templates, skills, defaultProfile]);

  async function hire(values: AgentInput) {
    const agent = await api.hireAgent(values);
    navigate(`/staff/${agent.id}`);
  }

  return (
    <>
      <p className="breadcrumb">
        <Link to="/staff">社員名簿</Link> / 社員を雇う
      </p>
      <h1>社員を雇う</h1>
      {error && <p className="status bad">{error}</p>}

      {initial === null ? (
        <>
          <p className="lead">どんな社員を雇いますか？役職を選ぶと、性格やスキルの初期値が入ります。</p>
          <div className="template-grid">
            {templates.map((t) => (
              <button key={t.key} type="button" className="template-card" onClick={() => setChosen(t.key)}>
                <Avatar name={t.title} color={t.avatar_color} />
                <div>
                  <div className="agent-name">{t.title}</div>
                  <div className="muted small">{t.description}</div>
                </div>
              </button>
            ))}
            <button type="button" className="template-card" onClick={() => setChosen(BLANK)}>
              <Avatar name="＋" color="c8" />
              <div>
                <div className="agent-name">白紙から</div>
                <div className="muted small">役職やスキルを自分で決める</div>
              </div>
            </button>
          </div>
        </>
      ) : (
        <section className="card">
          <AgentForm initial={initial} submitLabel="雇う" onSubmit={hire} onCancel={() => setChosen(null)} />
        </section>
      )}
    </>
  );
}
