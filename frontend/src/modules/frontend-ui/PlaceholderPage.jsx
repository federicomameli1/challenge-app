export default function PlaceholderPage({ title, hint }) {
  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-6 py-6">
      <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-900">
        <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
          Coming soon.
        </p>
        {hint ? (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>
        ) : null}
      </div>
    </section>
  );
}
