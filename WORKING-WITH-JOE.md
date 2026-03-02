# Working with Joe

**Joe McGinley** — Platform Engineer, Vancouver (PST)

---

## About me

I'm a platform engineer who builds and maintains infrastructure that other teams depend on. I care deeply about reliability, observability, and developer experience. Outside of work, I ride motorcycles, hike the trails around BC, travel whenever I can, and take too many photos. This homelab is where I experiment with ideas before they hit production — and where I nerd out on observability for fun.

## How I work

**I automate by default.** If I'm doing something twice, I'm writing tooling for it. GitOps, CI/CD pipelines, image updaters, code formatters — I'd rather invest time upfront in automation than burn it on repetitive tasks. My homelab reflects this: everything is declarative, version-controlled, and self-healing.

**I use AI as a force multiplier.** I'm an advocate for AI-assisted development and use tools like Claude Code extensively in my daily workflow. I've invested in building skills, hooks, and workflows around it. I believe AI tooling is most powerful when combined with strong engineering discipline — it amplifies good practices, it doesn't replace them.

**I have strong opinions, loosely held.** I care about doing things the right way — conventional commits, PR-based workflows, non-root containers, infrastructure as code. But I'm always open to hearing why a different approach might be better. Show me the data or the trade-off and I'll change my mind.

**I don't over-engineer.** Three similar lines of code is better than a premature abstraction. I build for what's needed now, not for hypothetical future requirements. Simple, focused, and correct beats clever every time.

## Communication

**I'm flexible — but I value intentionality.** I work across large timezone gaps, so async collaboration is important to me. That said, I genuinely enjoy pairing sessions and real-time problem-solving too. What matters most is that expectations are set and time is used productively:

- **Async:** Write clearly, provide context, link to the relevant code or doc. A good PR description saves everyone time.
- **Meetings:** Have an agenda. Capture action items. If a meeting could've been a message, it should've been.
- **Pairing:** Great for unblocking, exploring new territory, or just riffing on ideas. I'm always up for it.

## Feedback

**Give it to me straight.** I prefer direct, in-the-moment feedback — in PR reviews, in Slack, in person. Don't wait for a retro to tell me something could be better. I'll extend the same courtesy: if I leave pointed feedback on a PR, it comes from a place of caring about the work, not criticism of the person.

## What I value

- **Observability over guesswork.** Instrument it, trace it, alert on it. If you can't see what's happening, you can't fix what's broken.
- **Security as a default, not an afterthought.** Non-root containers, secrets management, least privilege — bake it in from the start.
- **Ownership and follow-through.** Ship it, monitor it, iterate on it. The work isn't done when the PR merges.
- **Clear documentation.** Future-you (and future-me) will thank you. ADRs, runbooks, and inline context matter.

## What frustrates me

- Skipping quality gates to move faster (spoiler: it's slower in the long run)
- Manual processes that should be automated
- Meetings without purpose or follow-up
- "It works on my machine" without reproducible builds
- Cutting corners on security or observability

## How to work with me effectively

1. **Share context.** A link to the code, a trace ID, a log snippet — context turns a 30-minute conversation into a 5-minute one.
2. **Propose solutions, not just problems.** I'm happy to help think through options, but come with at least a rough idea.
3. **Use async well.** If it's not urgent, a well-written message beats a tap on the shoulder. I'll respond thoughtfully.
4. **Challenge my assumptions.** I'd rather be wrong early than wrong in production.

## Fun facts

- This homelab runs a full Kubernetes cluster with ArgoCD, SigNoz, and more services than is probably reasonable
- I've been known to add observability to things that don't strictly need it — just because I can
- I think motorcycles and infrastructure have a lot in common: respect the fundamentals, maintain your machine, and always have a rollback plan
