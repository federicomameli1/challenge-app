import ReleaseDashboard from "./modules/frontend-ui/ReleaseDashboard.jsx";

export default function App() {
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-slate-50 text-slate-900">
      <div className="mx-auto w-full max-w-[1600px] shrink-0 px-6 pb-3 pt-6">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Hitachi Challenge
        </h1>
      </div>

      <hr className="mx-auto w-full max-w-[1600px] shrink-0 border-slate-200" />

      <div className="min-h-0 flex-1 overflow-hidden">
        <ReleaseDashboard />
      </div>
    </main>
  );
}
