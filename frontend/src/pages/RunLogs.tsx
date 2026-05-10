import { useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Code,
  Drawer,
  Group,
  Table,
  Tabs,
  Text,
} from "@mantine/core";
import { StatusBadge } from "../components/StatusBadge";
import type { AgentStep, LLMCall, ToolCall, WorkflowRun } from "../services/runsApi";
import { errorMessage, formatJson } from "./runDetailUtils";
import classes from "./RunDetail.module.css";

type LogDetail = {
  title: string;
  payload: unknown;
};

type ErrorRow = {
  id: string;
  source: string;
  type: string;
  message: string;
  payload: unknown;
};

type RunLogsProps = {
  run: WorkflowRun;
  steps: AgentStep[];
  toolCalls: ToolCall[];
  llmCalls: LLMCall[];
  agentExecution: Array<Record<string, unknown>>;
};

function buildErrorRows({
  run,
  steps,
  toolCalls,
  llmCalls,
}: Pick<RunLogsProps, "run" | "steps" | "toolCalls" | "llmCalls">): ErrorRow[] {
  const rows: ErrorRow[] = [];

  if (run.error) {
    rows.push({
      id: `${run.id}-run-error`,
      source: "Workflow Run",
      type: String(run.error.type ?? "run_error"),
      message: errorMessage(run.error),
      payload: run.error,
    });
  }

  for (const step of steps) {
    if (!step.error) continue;
    rows.push({
      id: `${step.id}-step-error`,
      source: `${step.agent_name} / ${step.step_type}`,
      type: String(step.error.type ?? "agent_step_error"),
      message: errorMessage(step.error),
      payload: {
        error: step.error,
        input: step.input,
        output: step.output,
      },
    });
  }

  for (const call of toolCalls) {
    if (!call.error) continue;
    rows.push({
      id: `${call.id}-tool-error`,
      source: call.tool_name,
      type: String(call.error.type ?? "tool_call_error"),
      message: errorMessage(call.error),
      payload: {
        error: call.error,
        arguments: call.arguments,
        response_summary: call.response_summary,
      },
    });
  }

  for (const call of llmCalls) {
    if (!call.purpose.endsWith("_failed")) continue;
    rows.push({
      id: `${call.id}-llm-error`,
      source: `${call.provider} / ${call.purpose}`,
      type: "llm_call_failed",
      message: "LLM 호출이 실패했습니다. Provider 에러 메시지는 실패한 Agent Step 또는 Workflow Run error에 저장됩니다.",
      payload: call,
    });
  }

  return rows;
}

function isDeterministicCollectionLlmRow(call: LLMCall) {
  return call.purpose === "data_summary" || call.purpose.startsWith("data_summary_");
}

export function RunLogs({
  run,
  steps,
  toolCalls,
  llmCalls,
  agentExecution,
}: RunLogsProps) {
  const [selectedLogDetail, setSelectedLogDetail] = useState<LogDetail | null>(null);
  const visibleLlmCalls = useMemo(
    () => llmCalls.filter((call) => !isDeterministicCollectionLlmRow(call)),
    [llmCalls]
  );
  const hiddenDeterministicCallCount = llmCalls.length - visibleLlmCalls.length;
  const errorRows = useMemo(
    () => buildErrorRows({ run, steps, toolCalls, llmCalls }),
    [run, steps, toolCalls, llmCalls]
  );

  return (
    <>
      <Tabs defaultValue={errorRows.length > 0 ? "errors" : "agents"}>
        <Tabs.List>
          <Tabs.Tab value="errors">
            <Group gap={6}>
              <span>Errors</span>
              {errorRows.length > 0 ? <Badge size="xs" color="red">{errorRows.length}</Badge> : null}
            </Group>
          </Tabs.Tab>
          <Tabs.Tab value="agents">Agent Execution</Tabs.Tab>
          <Tabs.Tab value="steps">Agent Steps</Tabs.Tab>
          <Tabs.Tab value="tools">Tool Calls</Tabs.Tab>
          <Tabs.Tab value="llm">LLM Calls</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="errors" pt="md">
          {errorRows.length > 0 ? (
            <Table striped verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Source</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Message</Table.Th>
                  <Table.Th>Details</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {errorRows.map((row) => (
                  <Table.Tr key={row.id}>
                    <Table.Td>{row.source}</Table.Td>
                    <Table.Td><Badge color="red" variant="light">{row.type}</Badge></Table.Td>
                    <Table.Td maw={520}>
                      <Text size="sm" lineClamp={3}>{row.message}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() => setSelectedLogDetail({ title: row.source, payload: row.payload })}
                      >
                        View
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          ) : (
            <Alert color="gray">이 run에 기록된 에러 로그가 없습니다.</Alert>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="agents" pt="md">
          <Table striped verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Agent</Table.Th>
                <Table.Th>Provider</Table.Th>
                <Table.Th>Model</Table.Th>
                <Table.Th>Tokens</Table.Th>
                <Table.Th>Cost</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {agentExecution.length > 0 ? (
                agentExecution.map((item, index) => (
                  <Table.Tr key={`${String(item.agent ?? "agent")}-${index}`}>
                    <Table.Td>{String(item.agent ?? "-")}</Table.Td>
                    <Table.Td><Badge variant="light">{String(item.provider ?? "-")}</Badge></Table.Td>
                    <Table.Td>{String(item.model ?? "-")}</Table.Td>
                    <Table.Td>{String(item.total_tokens ?? "-")}</Table.Td>
                    <Table.Td>${Number(item.cost_usd ?? 0).toFixed(6)}</Table.Td>
                  </Table.Tr>
                ))
              ) : (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text c="dimmed" ta="center">Agent execution metadata가 없습니다.</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="steps" pt="md">
          <Table striped verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Agent</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Latency</Table.Th>
                <Table.Th>Error</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {steps.map((step) => (
                <Table.Tr key={step.id}>
                  <Table.Td>{step.agent_name}</Table.Td>
                  <Table.Td>{step.step_type}</Table.Td>
                  <Table.Td><StatusBadge status={step.status} /></Table.Td>
                  <Table.Td>{step.latency_ms ?? 0}ms</Table.Td>
                  <Table.Td>
                    {step.error ? (
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        onClick={() =>
                          setSelectedLogDetail({
                            title: `${step.agent_name} error`,
                            payload: {
                              error: step.error,
                              input: step.input,
                              output: step.output,
                            },
                          })
                        }
                      >
                        View
                      </Button>
                    ) : (
                      "-"
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="tools" pt="md">
          <Table striped verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Tool</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Source</Table.Th>
                <Table.Th>Latency</Table.Th>
                <Table.Th>Summary</Table.Th>
                <Table.Th>Error</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {toolCalls.map((call) => (
                <Table.Tr key={call.id}>
                  <Table.Td>{call.tool_name}</Table.Td>
                  <Table.Td><StatusBadge status={call.status} /></Table.Td>
                  <Table.Td>{call.source ?? "-"}</Table.Td>
                  <Table.Td>{call.latency_ms ?? 0}ms</Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={2}>
                      {JSON.stringify(call.response_summary ?? call.error ?? {})}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {call.error ? (
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        onClick={() =>
                          setSelectedLogDetail({
                            title: `${call.tool_name} error`,
                            payload: {
                              error: call.error,
                              arguments: call.arguments,
                              response_summary: call.response_summary,
                            },
                          })
                        }
                      >
                        View
                      </Button>
                    ) : (
                      "-"
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="llm" pt="md">
          <Alert color="gray" mb="sm">
            LLM Calls에는 Gemini 호출과 legacy/offline agent call 기록을 표시합니다. Baseline TourAPI 수집, 색인, vector search 같은 deterministic 실행 기록은 Agent Steps와 Tool Calls에서 확인하세요.
            {hiddenDeterministicCallCount > 0
              ? ` 숨겨진 data_summary deterministic log ${hiddenDeterministicCallCount}건이 있습니다.`
              : ""}
          </Alert>
          <Table striped verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Provider</Table.Th>
                <Table.Th>Model</Table.Th>
                <Table.Th>Purpose</Table.Th>
                <Table.Th>Tokens</Table.Th>
                <Table.Th>Cost</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {visibleLlmCalls.length > 0 ? (
                visibleLlmCalls.map((call) => (
                  <Table.Tr key={call.id}>
                    <Table.Td>{call.provider}</Table.Td>
                    <Table.Td>{call.model}</Table.Td>
                    <Table.Td>{call.purpose}</Table.Td>
                    <Table.Td>{call.total_tokens}</Table.Td>
                    <Table.Td>${call.cost_usd.toFixed(6)}</Table.Td>
                  </Table.Tr>
                ))
              ) : (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text c="dimmed" ta="center">이 run에 표시할 LLM/agent call 기록이 없습니다.</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>
      </Tabs>

      <Drawer
        opened={selectedLogDetail !== null}
        onClose={() => setSelectedLogDetail(null)}
        position="right"
        size="lg"
        title={selectedLogDetail?.title ?? "Log detail"}
      >
        <Code block className={classes.jsonBlock}>
          {formatJson(selectedLogDetail?.payload)}
        </Code>
      </Drawer>
    </>
  );
}
