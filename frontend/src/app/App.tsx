import { LazyMotion, MotionConfig } from "motion/react";
const loadMotionFeatures=()=>import("../design/motionFeatures").then(m=>m.default);
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";
import { ShortLinkLanding } from "../phase4";
import { useAuth } from "../auth/authContext";
import { AuthProvider } from "../auth/authContext";
import { RequireRole, NotFoundPage } from "../components/RouteAccess";
import { AuthLayout } from "../layouts/AuthLayout";
import { PublicLayout } from "../layouts/PublicLayout";
import { WorkspaceLayout } from "../layouts/WorkspaceLayout";
import { workspaces } from "../navigation/workspaces";
import { LoginPage, RegistrationPage } from "../pages/AuthPages";
import { HomePage } from "../pages/HomePage";
import { SimulationProvider } from "../simulation/SimulationProvider";
const SystemDesignPage = lazy(() => import("../systemDesign/SystemDesignPage").then(module => ({ default: module.SystemDesignPage })));
const HospitalPage = lazy(() => import("../hospital/HospitalPage").then(module => ({ default: module.HospitalPage })));

function ShortLinkPage() {
  const { state, api } = useAuth();
  return <ShortLinkLanding api={api} authState={state.status} roleHints={state.status === "authenticated" ? state.roleHints : []} />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <PulseGridRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}

export function PulseGridRoutes() {
  return (
    <MotionConfig reducedMotion="user"><LazyMotion features={loadMotionFeatures} strict><SimulationProvider><Routes>
      <Route path="/system-design" element={<Suspense fallback={<p role="status">Loading System Design Lab…</p>}><SystemDesignPage /></Suspense>} />
      <Route path="/short-link" element={<ShortLinkPage />} />
      <Route element={<PublicLayout />}>
        <Route index element={<HomePage />} />
      </Route>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegistrationPage />} />
      </Route>
      {workspaces.map((workspace) => (
        <Route element={<RequireRole roles={workspace.roles} />} key={workspace.basePath}>
          <Route element={<WorkspaceLayout workspace={workspace} />} path={workspace.basePath}>
            <Route index element={<Navigate replace to="dashboard" />} />
            {workspace.pages.map((page) => (
              <Route
                element={<Suspense fallback={<p role="status">Loading hospital workspace…</p>}><HospitalPage key={`${workspace.basePath}/${page.path}`} page={page} workspace={workspace} /></Suspense>}
                key={page.path}
                path={page.path}
              />
            ))}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      ))}
      <Route path="*" element={<NotFoundPage />} />
    </Routes></SimulationProvider></LazyMotion></MotionConfig>
  );
}
