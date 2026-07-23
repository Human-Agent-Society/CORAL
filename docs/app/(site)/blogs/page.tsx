import Link from 'next/link';
import { blogPosts } from '@/lib/blogs';

const dateFormatter = new Intl.DateTimeFormat('en', {
  dateStyle: 'long',
  timeZone: 'UTC',
});

export default function BlogsPage() {
  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-16 md:py-24">
      <p className="text-sm font-medium uppercase tracking-[0.18em] text-fd-muted-foreground">
        Ideas and experiments
      </p>
      <h1 className="mt-3 text-4xl font-semibold text-fd-foreground md:text-6xl">Blogs</h1>
      <p className="mt-5 max-w-2xl text-lg leading-8 text-fd-muted-foreground">
        Research notes, results, and stories from building autonomous multi-agent systems with CORAL.
      </p>

      <div className="mt-12 grid gap-5">
        {blogPosts.map((post) => (
          <article key={post.slug} className="rounded-2xl border border-fd-border bg-fd-card p-7">
            <div className="flex flex-wrap items-center gap-3 text-sm text-fd-muted-foreground">
              <span className="rounded-full border border-fd-border bg-fd-background px-3 py-1 font-medium text-fd-foreground">
                {post.category}
              </span>
              <time dateTime={post.date}>{dateFormatter.format(new Date(`${post.date}T00:00:00Z`))}</time>
            </div>
            <h2 className="mt-5 text-2xl font-semibold text-fd-foreground md:text-3xl">
              <Link href={post.href} className="hover:underline">
                {post.title}
              </Link>
            </h2>
            <p className="mt-3 max-w-3xl leading-7 text-fd-muted-foreground">{post.summary}</p>
            <Link href={post.href} className="mt-6 inline-flex font-medium text-fd-foreground underline decoration-fd-border underline-offset-4">
              Read article →
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
