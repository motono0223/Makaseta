import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Render Markdown written by agents or kept in a 資料室. Raw HTML in the source is not rendered. */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
