import { useEffect, useState } from "react";
import { Button } from "./components/ui/button";

export default function App() {
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    if (!showToast) return;
    const timer = setTimeout(() => setShowToast(false), 2200);
    return () => clearTimeout(timer);
  }, [showToast]);

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center gap-6 px-6 text-center">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          Hitachi Challenge
        </h1>
        <p className="max-w-xl text-base text-slate-600 sm:text-lg">
          Simple demo page for CI/CD testing. Change the button color to
          validate pipeline updates.
        </p>
        <Button
          className="bg-yellow-600 text-white transition active:scale-95 active:shadow-inner hover:bg-red-700"
          onClick={() => setShowToast(true)}
        >
          Demo Button
        </Button>
      </div>
      <div
        className={`pointer-events-none fixed bottom-6 right-6 transform rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-lg transition-all duration-200 ${
          showToast
            ? "translate-y-0 opacity-100"
            : "translate-y-3 opacity-0"
        }`}
        role="status"
        aria-live="polite"
      >
        Button pressed. Pipeline test event fired.
      </div>
    </main>
  );
}
