import { Link } from "react-router-dom";

interface BrandProps {
  compact?: boolean;
}

export function Brand({ compact = false }: BrandProps) {
  return (
    <Link className={`brand${compact ? " brand--compact" : ""}`} to="/" aria-label="PulseGrid home">
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" role="presentation">
          <path className="brand-heart" d="M16 29S1 20 1 10C1 1 12-1 16 6 20-1 31 1 31 10c0 10-15 19-15 19Z"/><path d="M2 16h7l3-7 5 14 4-7h9" />
        </svg>
      </span>
      <span className="brand-name">PulseGrid</span>
    </Link>
  );
}
