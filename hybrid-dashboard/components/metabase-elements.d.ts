import type { DetailedHTMLProps, HTMLAttributes } from 'react';
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'metabase-dashboard': DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        token?: string;
        'dashboard-id'?: string;
        'with-title'?: 'true' | 'false';
        'with-downloads'?: 'true' | 'false';
      };
    }
  }
}
