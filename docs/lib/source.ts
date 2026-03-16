import { docs } from '@/.source';
import { loader } from 'fumadocs-core/source';
import { resolveFiles } from 'fumadocs-mdx';

// Build the source with files as a plain array.
// docs.toFumadocsSource() returns files as a function (fumadocs-mdx 11.x bug),
// but fumadocs-core 15.x expects an array. This workaround calls resolveFiles
// directly. The proper fix is upgrading to fumadocs-mdx 14.x + fumadocs-core 16.x.
export const source = loader({
  baseUrl: '/',
  source: { files: resolveFiles({ docs: docs.docs, meta: docs.meta }) },
});
