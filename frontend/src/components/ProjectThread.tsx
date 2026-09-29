import { useCallback, useState } from "react";
import { Message, Project, Task, api } from "../api";
import { usePolling } from "../usePolling";
import MessageList from "./MessageList";
import { useThread } from "./ThreadDrawer";

/** Everything said about this project's tasks, across its members. */
export default function ProjectThread({ project, tasks }: { project: Project; tasks: Task[] }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const openThread = useThread();
  const load = useCallback(() => {
    api.projectThread(project.id).then(setMessages).catch(() => undefined);
  }, [project.id]);
  const busy = tasks.some((t) => t.status === "in_progress");
  usePolling(load, busy ? 3000 : 8000);

  const agents = new Map(project.members.map((m) => [m.agent.id, m.agent]));
  const primary = project.members.find((m) => m.is_primary);

  return (
    <section className="card thread-card">
      <p className="muted small">
        このプロジェクトでの依頼・質問・報告の記録です。社員と話すときは、社員のアイコンからスレッドを開いてください。
        {primary && (
          <>
            {" "}
            <button type="button" className="link-button small" onClick={() => openThread(primary.agent.id)}>
              窓口の{primary.agent.name}さんと話す
            </button>
          </>
        )}
      </p>
      <MessageList messages={messages} agents={agents} />
    </section>
  );
}
