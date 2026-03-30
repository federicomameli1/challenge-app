import ReleaseDashboard from "./modules/frontend-ui/ReleaseDashboard.jsx";

export default function App() {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto flex max-w-4xl flex-col items-center justify-center gap-6 px-6 py-20 text-center">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          Hitachi Challenge
        </h1>
      </div>

      <hr className="mx-auto max-w-4xl border-slate-200" />

      <ReleaseDashboard />
    </main>
  );
}
