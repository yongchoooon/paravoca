import { AppShell, Badge, Burger, Button, Group, Stack, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import type { ReactNode } from "react";
import {
  IconAdjustments,
  IconBrush,
  IconChartBar,
  IconCoins,
  IconDatabase,
  IconRoute,
  IconSettings,
} from "@tabler/icons-react";
import classes from "./AppShellLayout.module.css";

export type AppSection =
  | "dashboard"
  | "workflow"
  | "data-sources"
  | "evaluation"
  | "costs"
  | "poster-studio"
  | "settings";

const navItems = [
  { id: "dashboard", label: "Dashboard", icon: IconChartBar },
  { id: "workflow", label: "Workflow Preview", icon: IconRoute },
  { id: "data-sources", label: "Data Sources", icon: IconDatabase, planned: true },
  { id: "evaluation", label: "Evaluation", icon: IconAdjustments, planned: true },
  { id: "costs", label: "Costs", icon: IconCoins, planned: true },
  { id: "poster-studio", label: "Poster Studio", icon: IconBrush, planned: true },
  { id: "settings", label: "Settings", icon: IconSettings, planned: true },
] satisfies Array<{
  id: AppSection;
  label: string;
  icon: typeof IconChartBar;
  planned?: boolean;
}>;

export function getAppSectionLabel(section: AppSection) {
  return navItems.find((item) => item.id === section)?.label ?? "Dashboard";
}

export function AppShellLayout({
  activeSection,
  onSectionChange,
  children,
}: {
  activeSection: AppSection;
  onSectionChange: (section: AppSection) => void;
  children: ReactNode;
}) {
  const [opened, { toggle }] = useDisclosure();
  const activeLabel = getAppSectionLabel(activeSection);

  function selectSection(section: AppSection) {
    onSectionChange(section);
    if (opened) {
      toggle();
    }
  }

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{
        width: 260,
        breakpoint: "sm",
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <div className={classes.brandMark}>AX</div>
            <div>
              <Text fw={700} size="sm">
                PARAVOCA AX
              </Text>
              <Text c="dimmed" size="xs">
                Agent Studio
              </Text>
            </div>
          </Group>
          <Text fw={700} size="sm" className={classes.sectionTitle}>
            {activeLabel}
          </Text>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <Stack gap={4}>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Button
                key={item.label}
                className={classes.navButton}
                variant={item.id === activeSection ? "light" : "subtle"}
                color="opsBlue"
                leftSection={<Icon size={17} />}
                rightSection={
                  item.planned ? (
                    <Badge size="xs" variant="light" color="gray">
                      예정
                    </Badge>
                  ) : undefined
                }
                onClick={() => selectSection(item.id)}
              >
                {item.label}
              </Button>
            );
          })}
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main className={classes.main}>{children}</AppShell.Main>
    </AppShell>
  );
}
