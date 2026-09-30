import { ProjectInput } from "../api";

type Props = { value: ProjectInput; onChange: (value: ProjectInput) => void };

export default function ProjectFields({ value, onChange }: Props) {
  const set = <K extends keyof ProjectInput>(key: K, v: ProjectInput[K]) => onChange({ ...value, [key]: v });
  return (
    <>
      <div className="form-row">
        <div className="field grow">
          <label htmlFor="project-name">プロジェクト名</label>
          <input id="project-name" value={value.name} maxLength={80} required onChange={(e) => set("name", e.target.value)}
            placeholder="例: 出張規程の見直し" />
        </div>
        <div className="field">
          <label htmlFor="project-due">期限</label>
          <input id="project-due" type="date" value={value.due_date ?? ""}
            onChange={(e) => set("due_date", e.target.value || null)} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="project-goal">目的</label>
        <textarea id="project-goal" rows={3} value={value.goal} onChange={(e) => set("goal", e.target.value)}
          placeholder="このプロジェクトで何を達成したいか" />
      </div>
      <div className="field">
        <label htmlFor="project-criteria">完了条件</label>
        <textarea id="project-criteria" rows={2} value={value.done_criteria}
          onChange={(e) => set("done_criteria", e.target.value)} placeholder="例: 改定案と新旧比較表ができている" />
      </div>
      <label className="toggle">
        <input type="checkbox" checked={value.require_plan_approval}
          onChange={(e) => set("require_plan_approval", e.target.checked)} />
        マネージャーが作ったタスク分解案は、オフィス長が承認してから実行する
      </label>
      <label className="toggle">
        <input type="checkbox" checked={value.auto_manage} onChange={(e) => set("auto_manage", e.target.checked)} />
        マネージャーにバックログを任せる（担当者のいないタスクの割り振りと、手が空いた社員への着手の指示）
      </label>
    </>
  );
}
