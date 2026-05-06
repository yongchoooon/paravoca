import { AppShell, Burger, Button, Group, Stack, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconAdjustments,
  IconChartBar,
  IconDatabase,
  IconRoute,
  IconSettings,
  IconTimeline,
} from "@tabler/icons-react";
import classes from "./AppShellLayout.module.css";

const navItems = [
  { label: "Dashboard", icon: IconChartBar },
  { label: "Workflows", icon: IconRoute },
  { label: "Runs", icon: IconTimeline },
  { label: "Data Sources", icon: IconDatabase },
  { label: "Evaluations", icon: IconAdjustments },
  { label: "Settings", icon: IconSettings },
];

export function AppShellLayout({ children }: { children: React.ReactNode }) {
  const [opened, { toggle }] = useDisclosure();

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
                TravelOps AX
              </Text>
              <Text c="dimmed" size="xs">
                Agent Studio
              </Text>
            </div>
          </Group>
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
                variant={item.label === "Dashboard" ? "light" : "subtle"}
                color="opsBlue"
                leftSection={<Icon size={17} />}
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

