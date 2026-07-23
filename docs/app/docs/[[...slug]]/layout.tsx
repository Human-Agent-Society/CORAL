import { source } from '@/lib/source';
import { DocsLayout, SidebarTrigger } from 'fumadocs-ui/layouts/docs';
import { Header } from 'fumadocs-ui/layouts/home';
import { baseOptions } from '@/lib/layout.shared';
import type { ReactNode } from 'react';

export default function Layout({ children }: { children: ReactNode }) {
  const siteOptions = baseOptions();

  return (
    <DocsLayout
      tree={source.getPageTree()}
      nav={{
        title: 'Documentation',
        url: '/docs/',
        component: (
          <Header
            {...siteOptions}
            nav={{
              ...siteOptions.nav,
              children: (
                <SidebarTrigger className="ms-auto inline-flex size-9 items-center justify-center rounded-md text-fd-muted-foreground transition-colors hover:bg-fd-accent hover:text-fd-accent-foreground md:hidden">
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="size-5"
                  >
                    <rect width="18" height="18" x="3" y="3" rx="2" />
                    <path d="M9 3v18" />
                  </svg>
                </SidebarTrigger>
              ),
            }}
          />
        ),
      }}
      links={[]}
      searchToggle={{ enabled: false }}
      themeSwitch={{ enabled: false }}
      containerProps={{ className: '[--fd-nav-height:56px]' }}
    >
      {children}
    </DocsLayout>
  );
}
