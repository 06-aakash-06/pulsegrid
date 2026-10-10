import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../auth/authContext";
import { RequireRole, NotFoundPage } from "../components/RouteAccess";
import { AuthLayout } from "../layouts/AuthLayout";
import { PublicLayout } from "../layouts/PublicLayout";
import { WorkspaceLayout } from "../layouts/WorkspaceLayout";
import { workspaces } from "../navigation/workspaces";
import { LoginPage, RegistrationPage } from "../pages/AuthPages";
import { HomePage } from "../pages/HomePage";
import { PlaceholderPage } from "../pages/PlaceholderPage";

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
    <Routes>
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
                element={<PlaceholderPage page={page} workspaceName={workspace.name} />}
                key={page.path}
                path={page.path}
              />
            ))}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      ))}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
