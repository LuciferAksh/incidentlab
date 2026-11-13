import { type ReactNode } from 'react';

export default function Metric({
  title,
  value,
  icon,
  footer,
  warning = false,
}: {
  title: string;
  value: string;
  icon: ReactNode;
  footer: string;
  warning?: boolean;
}) {
  return (
    <article className="metric">
      <div>
        <span>{title}</span>
        {icon}
      </div>
      <strong className={warning ? 'orange-text' : ''}>{value}</strong>
      <p>{footer}</p>
    </article>
  );
}
