import { cn } from '../../lib/cn';

export default function Card({ className, variant, ...props }) {
  const base = 'rounded-2xl border border-amber-500/30 backdrop-blur-md';
  const style = variant === 'numerology'
    ? cn(base, 'numerology-panel', className)
    : cn(base, 'bg-black/40 shadow-lg glass-card', className);
  return <div className={style} {...props} />;
}
