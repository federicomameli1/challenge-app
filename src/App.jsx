import ReleaseDashboard from "./modules/frontend-ui/ReleaseDashboard.jsx";

export default function App() {
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-slate-50 text-slate-900">
      <div className="mx-auto w-full max-w-[1820px] shrink-0 px-4 pb-2 pt-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Hitachi Challenge
        </h1>
      </div>

      <hr className="mx-auto w-full max-w-[1820px] shrink-0 border-slate-200" />

      <div className="min-h-0 flex-1 overflow-hidden">
        <ReleaseDashboard />
      </div>
    </main>
  );
}
