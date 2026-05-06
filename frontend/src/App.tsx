import { AppShellLayout } from "./components/AppShellLayout/AppShellLayout";
import { Dashboard } from "./pages/Dashboard";

export function App() {
  return (
    <AppShellLayout>
      <Dashboard />
    </AppShellLayout>
  );
}

