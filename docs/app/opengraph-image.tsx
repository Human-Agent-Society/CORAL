import { ImageResponse } from 'next/og';

export const alt = 'CORAL: open-source autoresearch powered by autonomous coding agents';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          alignItems: 'center',
          background: '#111821',
          color: '#edf2f7',
          display: 'flex',
          height: '100%',
          justifyContent: 'center',
          padding: '72px 88px',
          width: '100%',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', maxWidth: 1024 }}>
          <div
            style={{
              color: '#9eacba',
              display: 'flex',
              fontSize: 28,
              fontWeight: 600,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
            }}
          >
            CORAL · Open-source autoresearch
          </div>
          <div
            style={{
              display: 'flex',
              fontSize: 68,
              fontWeight: 700,
              letterSpacing: '-0.035em',
              lineHeight: 1.08,
              marginTop: 28,
            }}
          >
            Open-source autoresearch powered by autonomous coding agents.
          </div>
          <div
            style={{
              color: '#a9c7e8',
              display: 'flex',
              fontSize: 26,
              marginTop: 36,
            }}
          >
            Isolated worktrees · Continuous grading · Shared memory
          </div>
        </div>
      </div>
    ),
    size,
  );
}
