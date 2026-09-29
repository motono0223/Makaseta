import { useEffect, useRef } from "react";
import { AgentBrief, Message } from "../api";
import { formatDate } from "../format";
import Avatar from "./Avatar";
import Markdown from "./Markdown";

const KIND_LABEL: Partial<Record<Message["kind"], string>> = {
  question: "質問",
  report: "報告",
  review: "レビュー",
  instruction: "指示",
  answer: "回答",
};

type Props = { messages: Message[]; agents: Map<number, AgentBrief>; pending?: boolean };

/** Chat-style timeline: the office head on the right, agents on the left, system notes in the middle. */
export default function MessageList({ messages, agents, pending }: Props) {
  const end = useRef<HTMLDivElement>(null);
  const last = messages.at(-1)?.id;
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [last, pending]);

  return (
    <div className="messages">
      {messages.length === 0 && <p className="muted small center">まだやり取りはありません。</p>}
      {messages.map((m) => {
        if (m.sender === "system") {
          return <div key={m.id} className="msg-system">{m.body}<span> {formatDate(m.created_at)}</span></div>;
        }
        const agent = m.agent_id ? agents.get(m.agent_id) : undefined;
        const mine = m.sender === "manager";
        return (
          <div key={m.id} className={`msg ${mine ? "mine" : "theirs"} kind-${m.kind}`}>
            {!mine && agent && <Avatar name={agent.name} color={agent.avatar_color} size={28} />}
            <div className="bubble">
              <div className="msg-meta">
                {mine ? "オフィス長" : agent?.name ?? "社員"}
                {KIND_LABEL[m.kind] && <span className={`msg-kind kind-${m.kind}`}>{KIND_LABEL[m.kind]}</span>}
                <span>{formatDate(m.created_at)}</span>
              </div>
              {mine ? <div className="pre-line">{m.body}</div> : <Markdown>{m.body}</Markdown>}
            </div>
          </div>
        );
      })}
      {pending && <div className="msg theirs"><div className="bubble typing">返信を書いています…</div></div>}
      <div ref={end} />
    </div>
  );
}
