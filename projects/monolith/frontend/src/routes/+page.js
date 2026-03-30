export async function load({ fetch }) {
  const [todoRes, scheduleRes] = await Promise.all([
    fetch("/api/todo", { signal: AbortSignal.timeout(10000) }),
    fetch("/api/schedule/today", { signal: AbortSignal.timeout(10000) }).catch(
      () => ({ ok: false }),
    ),
  ]);
  return {
    todo: await todoRes.json(),
    schedule: scheduleRes.ok ? await scheduleRes.json() : [],
  };
}
