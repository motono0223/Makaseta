export default function ComingSoon({ title, what }: { title: string; what: string }) {
  return (
    <>
      <h1>{title}</h1>
      <section className="card">
        <p>準備中です。</p>
        {what && <p className="muted">ここには「{what}」が入ります。</p>}
      </section>
    </>
  );
}
