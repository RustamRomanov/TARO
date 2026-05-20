import { cn } from '../../lib/cn';

export default function Button({
  className,
  variant = 'primary',
  size = 'md',
  disabled,
  ...props
}) {
  const base =
    'inline-flex items-center justify-center rounded-xl font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400/50 disabled:opacity-40 disabled:pointer-events-none';
  const variants = {
    primary:
      'bg-gradient-to-r from-amber-300/25 via-amber-400/30 to-yellow-500/20 border border-amber-400/60 text-amber-200 hover:from-amber-300/35 hover:via-amber-400/40 hover:to-yellow-500/30',
    ghost: 'bg-transparent border border-white/15 text-white/80 hover:text-white',
  };
  const sizes = {
    md: 'px-4 py-3 text-sm',
    lg: 'px-6 py-3.5 text-base',
  };

  return (
    <button
      className={cn(base, variants[variant], sizes[size], className)}
      disabled={disabled}
      {...props}
    />
  );
}
