import { Link, Outlet } from "react-router-dom";
import { Brand } from "../components/Brand";

export function PublicLayout() {
  return (
    <div className="public-page">
      <header className="public-header">
        <Brand />
        <nav aria-label="Main navigation" className="public-nav">
          <Link className="text-link" to="/login">Sign in</Link>
          <Link className="button button--small" to="/register">Create patient account</Link>
        </nav>
      </header>
      <Outlet />
      <footer className="public-footer-note">
        <span>PulseGrid</span>
        <p>Educational prototype for one synthetic hospital. Not a certified clinical or emergency-response platform.</p>
      </footer>
    </div>
  );
}
