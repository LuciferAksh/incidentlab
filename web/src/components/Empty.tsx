import { type ReactNode } from 'react';
import { Activity } from 'lucide-react';

export default function Empty({
  icon,
  title,
  children,
}: {
  icon?: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      {icon || <Activity size={28} />}
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
