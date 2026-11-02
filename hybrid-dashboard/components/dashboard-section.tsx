import { useId, type ReactNode } from 'react';

export function DashboardSection({ title, description, actions, children, className = '' }: {
  title: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  const id = useId();
  return <section className={`analytics-section ${className}`} aria-labelledby={id}>
    <header className="section-header"><div><h2 id={id}>{title}</h2>{description && <p>{description}</p>}</div>{actions}</header>
    {children}
  </section>;
}
