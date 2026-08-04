import Link from 'next/link';
import { blogPosts } from '@/lib/blogs';
import { CORAL_DEFINITION, softwareApplicationJsonLd } from '@/lib/metadata';

const capabilities = [
  {
    title: 'Isolated workspaces',
    description:
      'Run agents in independent git worktrees so every idea can evolve without disrupting the others.',
  },
  {
    title: 'Continuous grading',
    description:
      'Score every committed attempt with your own grader and feed concrete results back into the loop.',
  },
  {
    title: 'Shared knowledge',
    description:
      'Carry attempts, notes, and reusable skills across agents through a persistent shared state.',
  },
] as const;

const agents = ['Claude Code', 'Codex', 'Cursor Agent', 'Kiro', 'OpenCode'] as const;
const examples = ['Optimization', 'Mathematics', 'Systems', 'GPU kernels', 'ML', 'Bio/ML'] as const;

export default function HomePage() {
  const latestPost = blogPosts[0];

  return (
    <div className="flex flex-1 flex-col">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareApplicationJsonLd) }}
      />
      <section className="mx-auto grid w-full max-w-6xl gap-10 px-6 py-20 md:grid-cols-[1.35fr_0.65fr] md:py-28">
        <div className="flex flex-col items-start">
          <p className="mb-5 rounded-full border border-fd-border bg-fd-card px-3 py-1 text-sm font-medium text-fd-muted-foreground">
            Open infrastructure for autoresearch
          </p>
          <h1 className="max-w-4xl text-5xl font-semibold tracking-tight text-fd-foreground md:text-7xl">
            Open-source autoresearch powered by autonomous coding agents.
          </h1>
          <p className="mt-7 max-w-2xl text-lg leading-8 text-fd-muted-foreground md:text-xl">
            {CORAL_DEFINITION}
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/docs/getting-started/"
              className="rounded-lg bg-fd-primary px-5 py-3 font-medium text-fd-primary-foreground transition-opacity hover:opacity-85"
            >
              Get started
            </Link>
            <Link
              href="/docs/what-is-coral/"
              className="rounded-lg border border-fd-border bg-fd-card px-5 py-3 font-medium text-fd-foreground transition-colors hover:bg-fd-accent"
            >
              What is CORAL?
            </Link>
            <Link
              href="https://github.com/Human-Agent-Society/CORAL"
              className="rounded-lg border border-fd-border bg-fd-card px-5 py-3 font-medium text-fd-foreground transition-colors hover:bg-fd-accent"
            >
              View on GitHub
            </Link>
          </div>
        </div>

        <div className="self-end rounded-2xl border border-fd-border bg-fd-card p-6 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
            The CORAL loop
          </p>
          <pre className="mt-5 overflow-x-auto rounded-xl border border-fd-border bg-fd-background p-5 text-sm leading-7 text-fd-foreground">
            <code>{`spawn agents
  ↓
commit experiments
  ↓
grade every attempt
  ↓
share what works
  ↺`}</code>
          </pre>
        </div>
      </section>

      <section className="border-y border-fd-border bg-fd-card/50">
        <div className="mx-auto w-full max-w-6xl px-6 py-20">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
            Built for continuous improvement
          </p>
          <h2 className="mt-3 text-3xl font-semibold text-fd-foreground md:text-4xl">
            The infrastructure around the agents
          </h2>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {capabilities.map((capability) => (
              <article
                key={capability.title}
                className="rounded-2xl border border-fd-border bg-fd-background p-6"
              >
                <h3 className="text-xl font-semibold text-fd-foreground">{capability.title}</h3>
                <p className="mt-3 leading-7 text-fd-muted-foreground">{capability.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-6xl gap-10 px-6 py-20 md:grid-cols-2 md:items-center">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
            How CORAL works
          </p>
          <h2 className="mt-3 text-3xl font-semibold text-fd-foreground md:text-4xl">
            A filesystem-native evolution loop
          </h2>
          <p className="mt-5 text-lg leading-8 text-fd-muted-foreground">
            The manager creates one worktree per agent and a grader daemon for evaluation. Agents
            submit commits, receive scores, and exchange discoveries through <code>.coral/public/</code>.
            Hidden grader state stays isolated under <code>.coral/private/</code>.
          </p>
          <Link
            href="/docs/concepts/architecture"
            className="mt-6 inline-flex font-medium text-fd-foreground underline decoration-fd-border underline-offset-4"
          >
            Explore the architecture →
          </Link>
        </div>
        <ol className="grid gap-3">
          {['Create isolated agent worktrees', 'Commit and submit an experiment', 'Grade the attempt safely', 'Share results and continue'].map(
            (step, index) => (
              <li key={step} className="flex items-center gap-4 rounded-xl border border-fd-border bg-fd-card p-4">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-fd-primary font-medium text-fd-primary-foreground">
                  {index + 1}
                </span>
                <span className="font-medium text-fd-foreground">{step}</span>
              </li>
            ),
          )}
        </ol>
      </section>

      <section className="border-y border-fd-border bg-fd-card/50">
        <div className="mx-auto grid w-full max-w-6xl gap-8 px-6 py-20 md:grid-cols-[0.8fr_1.2fr] md:items-center">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
              Quick Start
            </p>
            <h2 className="mt-3 text-3xl font-semibold text-fd-foreground md:text-4xl">
              Start an agent organization
            </h2>
            <p className="mt-4 leading-7 text-fd-muted-foreground">
              Install CORAL, scaffold a task, and launch your first run from a small YAML configuration.
            </p>
            <Link
              href="/docs/getting-started/"
              className="mt-6 inline-flex rounded-lg bg-fd-primary px-5 py-3 font-medium text-fd-primary-foreground transition-opacity hover:opacity-85"
            >
              Read the Quick Start
            </Link>
          </div>
          <pre className="overflow-x-auto rounded-2xl border border-fd-border bg-fd-background p-6 text-sm leading-7 text-fd-foreground shadow-sm">
            <code>{`curl -fsSL https://raw.githubusercontent.com/\
Human-Agent-Society/CORAL/main/install.sh | sh

coral init my-task
cd my-task
coral start -c task.yaml`}</code>
          </pre>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-6xl gap-8 px-6 py-20 md:grid-cols-2">
        <div className="rounded-2xl border border-fd-border bg-fd-card p-7">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
            Supported agents
          </p>
          <h2 className="mt-3 text-3xl font-semibold text-fd-foreground">Bring your coding agent</h2>
          <div className="mt-6 flex flex-wrap gap-2">
            {agents.map((agent) => (
              <span key={agent} className="rounded-full border border-fd-border bg-fd-background px-3 py-2 text-sm text-fd-foreground">
                {agent}
              </span>
            ))}
          </div>
          <Link href="/docs/guides/agent-runtimes" className="mt-6 inline-flex font-medium text-fd-foreground underline decoration-fd-border underline-offset-4">
            Configure agent runtimes →
          </Link>
        </div>
        <div className="rounded-2xl border border-fd-border bg-fd-card p-7">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
            Examples
          </p>
          <h2 className="mt-3 text-3xl font-semibold text-fd-foreground">Explore across domains</h2>
          <div className="mt-6 flex flex-wrap gap-2">
            {examples.map((example) => (
              <span key={example} className="rounded-full border border-fd-border bg-fd-background px-3 py-2 text-sm text-fd-foreground">
                {example}
              </span>
            ))}
          </div>
          <Link href="/docs/examples/" className="mt-6 inline-flex font-medium text-fd-foreground underline decoration-fd-border underline-offset-4">
            Browse example tasks →
          </Link>
        </div>
      </section>

      <section className="border-t border-fd-border bg-fd-card/50">
        <div className="mx-auto grid w-full max-w-6xl gap-6 px-6 py-20 md:grid-cols-2">
          <Link
            href="https://arxiv.org/abs/2604.01658v1"
            className="group rounded-2xl border border-fd-border bg-fd-background p-7 transition-colors hover:bg-fd-accent"
          >
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">Research</p>
            <h2 className="mt-3 text-2xl font-semibold text-fd-foreground">CORAL at COLM 2026</h2>
            <p className="mt-3 leading-7 text-fd-muted-foreground">
              Read the paper on autonomous multi-agent evolution for open-ended discovery.
            </p>
            <span className="mt-6 inline-flex font-medium text-fd-foreground">Read the paper →</span>
          </Link>
          <Link
            href={latestPost.href}
            className="group rounded-2xl border border-fd-border bg-fd-background p-7 transition-colors hover:bg-fd-accent"
          >
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">Latest blog</p>
            <h2 className="mt-3 text-2xl font-semibold text-fd-foreground">{latestPost.title}</h2>
            <p className="mt-3 leading-7 text-fd-muted-foreground">{latestPost.summary}</p>
            <span className="mt-6 inline-flex font-medium text-fd-foreground">Read the article →</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
