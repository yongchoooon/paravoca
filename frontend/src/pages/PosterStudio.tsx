import { useEffect, useMemo, useState } from "react";
import {
  Accordion,
  ActionIcon,
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Image,
  Loader,
  Modal,
  Paper,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconDownload,
  IconPhotoPlus,
  IconRefresh,
  IconTrash,
} from "@tabler/icons-react";
import { WorkflowRun, listWorkflowRuns } from "../services/runsApi";
import {
  DEFAULT_POSTER_INCLUDED_SECTIONS,
  DEFAULT_POSTER_STYLE,
  POSTER_SECTION_LABELS,
  PosterAsset,
  PosterIncludedSection,
  PosterOptions,
  PosterStylePresetId,
  createPoster,
  deletePoster,
  getPosterOptions,
  isActivePosterStatus,
  isCountedPosterStatus,
  listPosters,
  formatPosterCost,
  posterDownloadUrl,
  posterImageSrc,
} from "../services/postersApi";
import { formatKstDateTime } from "../utils/datetime";
import classes from "./PosterStudio.module.css";

type ProductOption = {
  id: string;
  title: string;
  one_liner?: string;
};

const SECTION_ORDER = Object.keys(POSTER_SECTION_LABELS) as PosterIncludedSection[];

export function PosterStudio() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [posters, setPosters] = useState<PosterAsset[]>([]);
  const [options, setOptions] = useState<PosterOptions | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [includedSections, setIncludedSections] = useState<PosterIncludedSection[]>(
    DEFAULT_POSTER_INCLUDED_SECTIONS
  );
  const [stylePreset, setStylePreset] = useState<PosterStylePresetId>(DEFAULT_POSTER_STYLE);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [previewPoster, setPreviewPoster] = useState<PosterAsset | null>(null);
  const [deletingPosterIds, setDeletingPosterIds] = useState<string[]>([]);

  async function loadData(options: { silent?: boolean } = {}) {
    try {
      if (!options.silent) {
        setLoading(true);
      }
      setError(null);
      const [nextOptions, nextRuns, nextPosters] = await Promise.all([
        getPosterOptions(),
        listWorkflowRuns(),
        listPosters(),
      ]);
      setOptions(nextOptions);
      setRuns(nextRuns);
      setPosters(nextPosters);
      setIncludedSections((current) =>
        current.length ? current : nextOptions.default_included_sections
      );
      setStylePreset((current) =>
        nextOptions.style_presets.some((preset) => preset.id === current)
          ? current
          : nextOptions.style_presets[0]?.id ?? DEFAULT_POSTER_STYLE
      );
      setSelectedRunId((current) => {
        if (current && nextRuns.some((run) => run.id === current)) return current;
        return nextRuns.find((run) => productOptionsForRun(run).length > 0)?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Poster Studio 데이터를 불러오지 못했습니다.");
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  const productOptions = useMemo(
    () => (selectedRun ? productOptionsForRun(selectedRun) : []),
    [selectedRun]
  );

  useEffect(() => {
    setSelectedProductId((current) => {
      if (current && productOptions.some((product) => product.id === current)) return current;
      return productOptions[0]?.id ?? null;
    });
  }, [productOptions]);

  const selectedProduct = productOptions.find((product) => product.id === selectedProductId) ?? null;
  const maxPostersPerProduct = options?.max_posters_per_product ?? 3;
  const selectedProductPosters = useMemo(
    () =>
      posters.filter(
        (poster) =>
          poster.run_id === selectedRunId &&
          poster.product_id === selectedProductId &&
          isCountedPosterStatus(poster.status)
      ),
    [posters, selectedRunId, selectedProductId]
  );
  const selectedProductPosterCount = selectedProductPosters.length;
  const selectedProductAtLimit = selectedProductPosterCount >= maxPostersPerProduct;
  const hasActivePosters = useMemo(
    () => posters.some((poster) => isActivePosterStatus(poster.status)),
    [posters]
  );

  const latestPosters = useMemo(
    () =>
      posters
        .slice()
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [posters]
  );

  useEffect(() => {
    if (!hasActivePosters) return;
    const timer = window.setInterval(() => {
      void refreshPosters();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasActivePosters]);

  async function handleGenerate() {
    if (!selectedRunId || !selectedProductId) {
      setGenerationError("포스터를 만들 run과 product를 먼저 선택해 주세요.");
      return;
    }
    try {
      setGenerating(true);
      setGenerationError(null);
      const poster = await createPoster(selectedRunId, selectedProductId, {
        style_preset: stylePreset,
        included_sections: includedSections,
      });
      setPosters((current) => [poster, ...current.filter((item) => item.id !== poster.id)]);
      notifications.show({
        title: "포스터 생성 시작",
        message: "백그라운드에서 포스터 초안 이미지를 생성합니다. 완료되면 목록에 이미지가 표시됩니다.",
        color: "blue",
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "포스터 생성에 실패했습니다.";
      setGenerationError(message);
      notifications.show({ title: "포스터 생성 실패", message, color: "red" });
      void refreshPosters();
    } finally {
      setGenerating(false);
    }
  }

  async function handleDeletePoster(poster: PosterAsset) {
    try {
      setDeletingPosterIds((current) => [...current, poster.id]);
      await deletePoster(poster.id);
      setPosters((current) => current.filter((item) => item.id !== poster.id));
      setPreviewPoster((current) => (current?.id === poster.id ? null : current));
      notifications.show({
        title: "포스터 삭제",
        message: "저장된 포스터 초안 기록을 삭제했습니다.",
        color: "gray",
      });
    } catch (err) {
      notifications.show({
        title: "포스터 삭제 실패",
        message: err instanceof Error ? err.message : "포스터를 삭제하지 못했습니다.",
        color: "red",
      });
    } finally {
      setDeletingPosterIds((current) => current.filter((id) => id !== poster.id));
    }
  }

  async function refreshPosters() {
    try {
      const nextPosters = await listPosters();
      setPosters(nextPosters);
    } catch {
      // The generation error is already visible; avoid replacing it with a refresh error.
    }
  }

  function toggleSection(section: PosterIncludedSection, checked: boolean) {
    setIncludedSections((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(section);
      } else {
        next.delete(section);
      }
      return SECTION_ORDER.filter((item) => next.has(item));
    });
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Poster Studio</Title>
          <Text size="sm" c="dimmed">
            run과 product에 연결된 생성 포스터 초안을 관리합니다.
          </Text>
        </div>
        <Button
          variant="light"
          leftSection={<IconRefresh size={16} />}
          onClick={() => void loadData({ silent: true })}
          disabled={loading || generating}
        >
          새로고침
        </Button>
      </Group>

      <Alert color="gray">
        생성되는 이미지는 포스터 초안입니다. 현재는 정해진 스타일로만 생성할 수 있으며, 자유 커스터마이즈는 후속 단계에서 제공 예정입니다.
      </Alert>

      {error ? (
        <Alert color="red" icon={<IconAlertCircle size={16} />}>
          {error}
        </Alert>
      ) : null}

      <div className={classes.studioGrid}>
        <Paper withBorder p="md" className={classes.createPanel}>
          <Stack gap="sm">
            <Group justify="space-between">
              <Text fw={700}>새 포스터 생성</Text>
              {options ? (
                <Badge variant="light" color="gray">
                  {options.image_size} · {options.image_quality}
                </Badge>
              ) : null}
            </Group>
            <Select
              label="Run 선택"
              placeholder="포스터를 만들 run"
              data={runsWithProducts(runs).map((run) => ({
                value: run.id,
                label: runLabel(run),
              }))}
              value={selectedRunId}
              onChange={setSelectedRunId}
              searchable
              nothingFoundMessage="상품이 있는 run이 없습니다."
              disabled={loading || generating}
            />
            <Select
              label="Product 선택"
              placeholder="상품 선택"
              data={productOptions.map((product) => ({
                value: product.id,
                label: product.title,
              }))}
              value={selectedProductId}
              onChange={setSelectedProductId}
              searchable
              nothingFoundMessage="선택한 run에 상품이 없습니다."
              disabled={!selectedRunId || loading || generating}
            />
            {selectedProduct ? (
              <Text size="sm" c="dimmed" lineClamp={2}>
                {selectedProduct.one_liner || selectedProduct.title}
              </Text>
            ) : null}

            <Stack gap={6}>
              <Text fw={700} size="sm">포함할 내용</Text>
              {SECTION_ORDER.map((section) => (
                <Checkbox
                  key={section}
                  label={POSTER_SECTION_LABELS[section]}
                  checked={includedSections.includes(section)}
                  onChange={(event) => toggleSection(section, event.currentTarget.checked)}
                  disabled={generating}
                />
              ))}
            </Stack>

            <Select
              label="스타일"
              data={(options?.style_presets ?? []).map((preset) => ({
                value: preset.id,
                label: preset.label,
              }))}
              value={stylePreset}
              onChange={(value) => setStylePreset((value as PosterStylePresetId) ?? DEFAULT_POSTER_STYLE)}
              disabled={!options || generating}
            />
            {options?.style_presets.find((preset) => preset.id === stylePreset)?.description ? (
              <Text size="xs" c="dimmed">
                {options.style_presets.find((preset) => preset.id === stylePreset)?.description}
              </Text>
            ) : null}

            <Alert color="blue" variant="light">
              포스터 초안 이미지는 상품 1개당 최대 {maxPostersPerProduct}개까지 저장됩니다. 현재 선택한 상품은 {selectedProductPosterCount}개를 사용 중입니다.
              크기는 {options?.image_size ?? "1024x1536"} portrait로 고정되어 있습니다.
            </Alert>

            {generationError ? (
              <Alert color="red" icon={<IconAlertCircle size={16} />}>
                {generationError}
              </Alert>
            ) : null}

            <Button
              leftSection={generating ? <Loader size={16} /> : <IconPhotoPlus size={16} />}
              onClick={handleGenerate}
              disabled={
                !selectedRunId ||
                !selectedProductId ||
                includedSections.length === 0 ||
                generating ||
                selectedProductAtLimit
              }
            >
              {generating ? "포스터 생성 요청 중" : "포스터 생성"}
            </Button>
            {selectedProductAtLimit ? (
              <Text size="sm" c="dimmed">
                이 상품은 포스터 초안 {maxPostersPerProduct}개를 모두 사용 중입니다. 기존 포스터를 삭제하면 하나 더 만들 수 있습니다.
              </Text>
            ) : null}
            {generating ? (
              <Text size="sm" c="dimmed">
                생성 작업을 등록하고 있습니다. 등록 후에는 이 화면을 이동하거나 새로고침해도 백그라운드에서 계속 진행됩니다.
              </Text>
            ) : null}
          </Stack>
        </Paper>

        <Stack gap="md">
          <Group justify="space-between">
            <div>
              <Text fw={700}>최근 포스터</Text>
              <Text size="sm" c="dimmed">
                이미지가 있는 항목은 바로 미리보기로 표시됩니다. 이미지를 누르면 크게 볼 수 있습니다.
              </Text>
            </div>
            <Badge variant="light" color="opsBlue">
              {latestPosters.length}개
            </Badge>
          </Group>

          {loading ? (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              {[0, 1, 2].map((item) => (
                <Skeleton key={item} className={classes.skeletonFrame} radius="md" />
              ))}
            </SimpleGrid>
          ) : latestPosters.length === 0 && !generating ? (
            <Paper withBorder p="lg">
              <Text fw={700}>생성된 포스터가 없습니다.</Text>
              <Text size="sm" c="dimmed">
                왼쪽 패널에서 run과 product를 선택한 뒤 포스터를 생성하세요.
              </Text>
            </Paper>
          ) : (
            <div className={classes.posterGrid}>
              {latestPosters.map((poster) => (
                <PosterCard
                  key={poster.id}
                  poster={poster}
                  usdKrwRate={options?.usd_krw_rate}
                  deleting={deletingPosterIds.includes(poster.id)}
                  onDelete={() => void handleDeletePoster(poster)}
                  onPreview={() => setPreviewPoster(poster)}
                />
              ))}
            </div>
          )}
        </Stack>
      </div>

      <Modal
        opened={previewPoster !== null}
        onClose={() => setPreviewPoster(null)}
        title={previewPoster?.product_title ?? "포스터 초안 이미지"}
        size="xl"
      >
        {previewPoster ? (
          <Stack gap="sm">
            <Group gap="xs">
              <Badge variant="light" color="gray">{previewPoster.style_preset}</Badge>
              <Badge variant="light" color="blue">포스터 초안 이미지</Badge>
            </Group>
            <Image
              src={posterImageSrc(previewPoster)}
              alt={previewPoster.product_title}
              fit="contain"
              mah="75vh"
            />
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}

function PosterCard({
  poster,
  usdKrwRate,
  deleting,
  onDelete,
  onPreview,
}: {
  poster: PosterAsset;
  usdKrwRate?: number;
  deleting: boolean;
  onDelete: () => void;
  onPreview: () => void;
}) {
  const imageSrc = posterImageSrc(poster);
  const failedMessage = poster.error?.message ?? "포스터 생성에 실패했습니다.";
  const includedSections = poster.included_sections
    .map((section) => POSTER_SECTION_LABELS[section] ?? section)
    .join(", ");

  return (
    <Paper withBorder p="sm" className={classes.posterCard}>
      <Stack gap="sm">
        <div className={classes.posterImageFrame}>
          {poster.status === "succeeded" && imageSrc ? (
            <button
              type="button"
              className={classes.posterImageButton}
              onClick={onPreview}
              aria-label={`${poster.product_title} 포스터 크게 보기`}
            >
              <Image src={imageSrc} alt={poster.product_title} w="100%" h="100%" fit="cover" />
            </button>
          ) : poster.status === "failed" ? (
            <Stack h="100%" align="center" justify="center" p="md">
              <Badge color="red" variant="light">failed</Badge>
              <Text size="sm" ta="center" c="dimmed" lineClamp={4}>
                {failedMessage}
              </Text>
            </Stack>
          ) : (
            <Stack h="100%" align="center" justify="center">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">생성 중</Text>
            </Stack>
          )}
        </div>

        <div className={classes.posterMeta}>
          <Group gap="xs" mb={4}>
            <Badge variant="light" color={poster.status === "succeeded" ? "green" : poster.status === "failed" ? "red" : "blue"}>
              {poster.status}
            </Badge>
            <Badge variant="light" color="gray">{poster.style_preset}</Badge>
            <Badge variant="light" color="blue">포스터 초안</Badge>
          </Group>
          <Text fw={700} lineClamp={2}>{poster.product_title}</Text>
          <Text size="xs" c="dimmed" lineClamp={2}>
            옵션: {includedSections || "선택 없음"}
          </Text>
          <Text size="xs" c="dimmed" lineClamp={1}>
            {poster.run_id}
          </Text>
          <Text size="xs" c="dimmed">
            {formatKstDateTime(poster.created_at)}
          </Text>
        </div>

        <Group gap="xs">
          <Button
            size="xs"
            variant="light"
            component="a"
            href={posterDownloadUrl(poster.id)}
            leftSection={<IconDownload size={14} />}
            disabled={poster.status !== "succeeded"}
          >
            다운로드
          </Button>
          <Tooltip label={isActivePosterStatus(poster.status) ? "생성 중인 포스터는 완료 후 삭제할 수 있습니다." : "삭제"}>
            <ActionIcon
              variant="light"
              color="red"
              aria-label="포스터 삭제"
              loading={deleting}
              disabled={isActivePosterStatus(poster.status)}
              onClick={onDelete}
            >
              <IconTrash size={15} />
            </ActionIcon>
          </Tooltip>
        </Group>

        <Accordion variant="contained">
          <Accordion.Item value="metadata">
            <Accordion.Control>Developer metadata</Accordion.Control>
            <Accordion.Panel>
              <Stack gap="xs">
                <Text size="xs" c="dimmed">
                  model={poster.image_model}, latency={poster.latency_ms ?? "-"}ms, cost≈{formatPosterCost(poster, usdKrwRate)}
                </Text>
                {poster.error ? (
                  <Text size="xs" c="red" className={classes.monoBlock}>
                    {JSON.stringify(poster.error, null, 2)}
                  </Text>
                ) : null}
                <Text size="xs" className={classes.monoBlock}>
                  {JSON.stringify(poster.provider_response_summary, null, 2)}
                </Text>
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Stack>
    </Paper>
  );
}

function runsWithProducts(runs: WorkflowRun[]) {
  return runs.filter((run) => productOptionsForRun(run).length > 0);
}

function productOptionsForRun(run: WorkflowRun): ProductOption[] {
  const finalOutput = run.final_output;
  const rawProducts = finalOutput?.["products"];
  const products = Array.isArray(rawProducts) ? rawProducts : [];
  return products
    .filter((product): product is Record<string, unknown> => Boolean(product && typeof product === "object"))
    .map((product) => ({
      id: String(product.id ?? ""),
      title: String(product.title ?? product.id ?? "Untitled product"),
      one_liner: typeof product.one_liner === "string" ? product.one_liner : undefined,
    }))
    .filter((product) => product.id);
}

function runLabel(run: WorkflowRun) {
  const message = typeof run.input?.message === "string" ? run.input.message : run.id;
  return `${message.slice(0, 48)} · ${run.id.slice(0, 14)}`;
}
