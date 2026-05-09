import { useState } from "react";
import { AppShellLayout } from "./components/AppShellLayout/AppShellLayout";
import type { AppSection } from "./components/AppShellLayout/AppShellLayout";
import { Dashboard } from "./pages/Dashboard";

export function App() {
  const [activeSection, setActiveSection] = useState<AppSection>("dashboard");

  return (
    <AppShellLayout activeSection={activeSection} onSectionChange={setActiveSection}>
      <Dashboard activeSection={activeSection} />
    </AppShellLayout>
  );
}
