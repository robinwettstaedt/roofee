type DatasetSummary = {
  name: string;
  file_count: number;
  files: string[];
};

type ApiState = {
  ok: boolean;
  datasets: DatasetSummary[];
};

async function getApiState(): Promise<ApiState> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const [healthResponse, datasetsResponse] = await Promise.all([
      fetch(`${apiUrl}/api/health`, { cache: "no-store" }),
      fetch(`${apiUrl}/api/data/datasets`, { cache: "no-store" }),
    ]);

    if (!healthResponse.ok || !datasetsResponse.ok) {
      return { ok: false, datasets: [] };
    }

    return {
      ok: true,
      datasets: await datasetsResponse.json(),
    };
  } catch {
    return { ok: false, datasets: [] };
  }
}

export default async function Home() {
  const api = await getApiState();

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-8 text-zinc-950">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <header className="flex flex-col gap-3 border-b border-zinc-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-medium text-teal-700">Roofee</p>
            <h1 className="mt-2 text-4xl font-semibold tracking-normal">
              Hackathon Workspace
            </h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                api.ok ? "bg-emerald-500" : "bg-amber-500"
              }`}
            />
            <span className="text-zinc-700">
              API {api.ok ? "connected" : "not running"}
            </span>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <p className="text-sm text-zinc-600">Frontend</p>
            <p className="mt-2 text-2xl font-semibold">Next.js</p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <p className="text-sm text-zinc-600">Backend</p>
            <p className="mt-2 text-2xl font-semibold">FastAPI</p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <p className="text-sm text-zinc-600">Datasets</p>
            <p className="mt-2 text-2xl font-semibold">{api.datasets.length}</p>
          </div>
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Backend Data</h2>
            <code className="rounded bg-zinc-100 px-2 py-1 text-sm text-zinc-700">
              /api/data/datasets
            </code>
          </div>

          {api.datasets.length > 0 ? (
            <div className="grid gap-3">
              {api.datasets.map((dataset) => (
                <article
                  key={dataset.name}
                  className="rounded-lg border border-zinc-200 bg-white p-5"
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <h3 className="text-lg font-medium">{dataset.name}</h3>
                    <span className="text-sm text-zinc-600">
                      {dataset.file_count} files
                    </span>
                  </div>
                  <ul className="mt-4 grid gap-2 text-sm text-zinc-700 sm:grid-cols-2">
                    {dataset.files.map((file) => (
                      <li key={file} className="rounded bg-zinc-50 px-3 py-2">
                        {file}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-6 text-zinc-600">
              No dataset summaries available.
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
