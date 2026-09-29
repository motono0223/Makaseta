import { DragEvent, useState } from "react";
import { ProjectMember, Task, TaskStatus } from "../api";
import { PRIORITY, TASK_COLUMNS } from "../labels";
import Avatar from "./Avatar";

type Props = {
  tasks: Task[];
  members: ProjectMember[];
  onOpen: (task: Task) => void;
  onAdd: () => void;
  onMove: (task: Task, status: TaskStatus, position: number) => void;
};

export default function Kanban({ tasks, members, onOpen, onAdd, onMove }: Props) {
  const [dragging, setDragging] = useState<Task | null>(null);
  const [over, setOver] = useState<{ status: TaskStatus; index: number } | null>(null);
  const agentById = new Map(members.map((m) => [m.agent.id, m.agent]));

  const column = (status: TaskStatus) =>
    tasks.filter((t) => t.status === status).sort((a, b) => a.rank - b.rank || a.id - b.id);

  function drop(e: DragEvent, status: TaskStatus) {
    e.preventDefault();
    if (dragging && over) {
      // Dropping below its own position within the same column shifts the index by one.
      const current = column(status).findIndex((t) => t.id === dragging.id);
      const index = current >= 0 && current < over.index ? over.index - 1 : over.index;
      onMove(dragging, status, index);
    }
    setDragging(null);
    setOver(null);
  }

  return (
    <div className="kanban">
      {TASK_COLUMNS.map(({ status, label }) => {
        const items = column(status);
        return (
          <section
            key={status}
            className={`kanban-column${over?.status === status ? " drop-target" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (over?.status !== status) setOver({ status, index: items.length });
            }}
            onDrop={(e) => drop(e, status)}
          >
            <header className="kanban-head">
              <span>{label}</span>
              <span className="muted small">{items.length}</span>
            </header>
            {items.map((t, index) => {
              const assignee = t.assignee_id ? agentById.get(t.assignee_id) : undefined;
              return (
                <article
                  key={t.id}
                  className={`task-card${dragging?.id === t.id ? " dragging" : ""}${
                    over?.status === status && over.index === index ? " insert-before" : ""
                  }`}
                  draggable
                  onDragStart={() => setDragging(t)}
                  onDragEnd={() => {
                    setDragging(null);
                    setOver(null);
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setOver({ status, index });
                  }}
                  onClick={() => onOpen(t)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onOpen(t)}
                >
                  <div className="task-title">{t.title}</div>
                  <div className="task-meta">
                    {t.priority !== "normal" && <span className={`chip priority-${t.priority}`}>優先度 {PRIORITY[t.priority]}</span>}
                    {t.due_date && <span className="muted small">期限 {t.due_date}</span>}
                    <span className="push-right">
                      {assignee ? (
                        <span title={assignee.name}><Avatar name={assignee.name} color={assignee.avatar_color} size={24} /></span>
                      ) : (
                        <span className="muted small">未割当</span>
                      )}
                    </span>
                  </div>
                </article>
              );
            })}
            {status === "backlog" && (
              <button type="button" className="add-task" onClick={onAdd}>＋ タスクを追加</button>
            )}
          </section>
        );
      })}
    </div>
  );
}
