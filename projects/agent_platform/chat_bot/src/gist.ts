export class GistClient {
  constructor(private token: string) {}

  async create(description: string, content: string): Promise<string> {
    const res = await fetch("https://api.github.com/gists", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        description,
        public: false,
        files: { "output.md": { content } },
      }),
    });
    if (!res.ok) throw new Error(`GitHub API error: ${res.status}`);
    const data = (await res.json()) as { html_url: string };
    return data.html_url;
  }
}
