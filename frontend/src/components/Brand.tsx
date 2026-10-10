import { Link } from "react-router-dom";

interface BrandProps {
  compact?: boolean;
}

export function Brand({ compact = false }: BrandProps) {
  return (
    <Link className={`brand${compact ? " brand--compact" : ""}`} to="/" aria-label="PulseGrid home">
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" role="presentation">
          <path d="M4 16h6l3.2-7 5.1 14 3.1-7H28" />
        </svg>
      </span>
      <span className="brand-name">PulseGrid</span>
    </Link>
  );
}
