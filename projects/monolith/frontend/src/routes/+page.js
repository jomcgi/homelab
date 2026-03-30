export async function load({ fetch }) {
  const res = await fetch("/api/todo", { signal: AbortSignal.timeout(10000) });
  return { todo: await res.json() };
}
