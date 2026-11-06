"use client";

import dynamic from "next/dynamic";

const Studio = dynamic(() => import("./studio"), {
  ssr: false,
  loading: () => (
    <main className="loading-page">
      <span className="brand">✳ Story Studio</span>
      <p>Opening your writing space…</p>
    </main>
  ),
});

export default function StudioEntry({ signUp = false }: { signUp?: boolean }) {
  return <Studio signUp={signUp} />;
}
