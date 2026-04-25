"use client";
import dynamic from "next/dynamic";

const DesignerApp = dynamic(() => import("@/components/DesignerApp"), {
  ssr: false,
  loading: () => (
    <div className="grid h-screen place-items-center text-zinc-500">Loading…</div>
  ),
});

export default function Page() {
  return <DesignerApp />;
}
