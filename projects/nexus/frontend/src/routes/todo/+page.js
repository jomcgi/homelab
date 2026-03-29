export async function load({ fetch }) {
  const [todoRes, datesRes] = await Promise.all([
    fetch("/api/todo", { signal: AbortSignal.timeout(10000) }),
    fetch("/api/todo/dates", { signal: AbortSignal.timeout(10000) }),
  ]);
  return {
    todo: await todoRes.json(),
    dates: await datesRes.json(),
  };
}
