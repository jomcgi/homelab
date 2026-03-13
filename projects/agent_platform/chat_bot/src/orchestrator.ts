export interface Job {
  id: string;
  status: string;
  created_at: string;
}

export interface JobOutput {
  output: string;
  result?: {
    summary?: string;
  };
  status: string;
}

export class OrchestratorClient {
  constructor(private baseUrl: string) {}

  async submitJob(task: string): Promise<Job> {
    const res = await fetch(`${this.baseUrl}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, source: "discord" }),
    });
    if (!res.ok)
      throw new Error(`Orchestrator error: ${res.status} ${await res.text()}`);
    return res.json() as Promise<Job>;
  }

  async getJobOutput(jobId: string): Promise<JobOutput> {
    const res = await fetch(`${this.baseUrl}/jobs/${jobId}/output`);
    if (!res.ok) throw new Error(`Orchestrator error: ${res.status}`);
    return res.json() as Promise<JobOutput>;
  }
}
