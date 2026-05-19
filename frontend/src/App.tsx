import { useCallback, useEffect, useState } from "react";
import { AppShellLayout } from "./components/AppShellLayout/AppShellLayout";
import type { AppSection } from "./components/AppShellLayout/AppShellLayout";
import { Dashboard } from "./pages/Dashboard";
import { EvaluationDashboard } from "./pages/EvaluationDashboard/EvaluationDashboard";

const APP_SECTIONS = new Set<AppSection>([
  "dashboard",
  "workflow",
  "data-sources",
  "evaluation",
  "costs",
  "poster-studio",
  "settings",
]);

function sectionFromUrl(): AppSection {
  const section = new URLSearchParams(window.location.search).get("section");
  return APP_SECTIONS.has(section as AppSection) ? (section as AppSection) : "dashboard";
}

function writeSectionToUrl(section: AppSection) {
  const url = new URL(window.location.href);
  if (section === "dashboard") {
    url.searchParams.delete("section");
  } else {
    url.searchParams.set("section", section);
  }
  window.history.pushState({ section }, "", url);
}

export function App() {
  const [activeSection, setActiveSection] = useState<AppSection>(() => sectionFromUrl());

  useEffect(() => {
    function handlePopState() {
      setActiveSection(sectionFromUrl());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const changeSection = useCallback(
    (section: AppSection) => {
      if (section !== activeSection) {
        writeSectionToUrl(section);
      }
      setActiveSection(section);
    },
    [activeSection]
  );

  return (
    <AppShellLayout activeSection={activeSection} onSectionChange={changeSection}>
      {activeSection === "evaluation" ? (
        <EvaluationDashboard />
      ) : (
        <Dashboard activeSection={activeSection} />
      )}
    </AppShellLayout>
  );
}
