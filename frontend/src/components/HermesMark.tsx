interface HermesMarkProps {
  className?: string;
}

export function HermesMark({ className = '' }: HermesMarkProps) {
  return (
    <span className={`hermes-logo-mark${className ? ` ${className}` : ''}`} aria-hidden="true">
      <img src="/favicon.svg" alt="" aria-hidden="true" />
    </span>
  );
}
