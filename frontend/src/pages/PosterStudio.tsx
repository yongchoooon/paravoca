import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Checkbox,
  Drawer,
  Group,
  Image,
  Loader,
  Modal,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconChevronDown,
  IconChevronUp,
  IconDownload,
  IconPhotoPlus,
  IconRefresh,
  IconTrash,
  IconZoomIn,
  IconZoomOut,
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
  posterDownloadUrl,
  posterImageSrc,
} from "../services/postersApi";
import { StatusBadge } from "../components/StatusBadge";
import { formatKstDateTime } from "../utils/datetime";
import { RunDetail } from "./RunDetail";
import classes from "./PosterStudio.module.css";

type ProductOption = {
  id: string;
  title: string;
  one_liner?: string;
};

type RunSelectionEntry = {
  run: WorkflowRun;
  indent: boolean;
};

type PosterImageCandidate = {
  image_url: string;
  thumbnail_url?: string;
  title: string;
  source: string;
  relevance_label: string;
  relevance_rank: number;
};

const SECTION_ORDER = Object.keys(POSTER_SECTION_LABELS) as PosterIncludedSection[];
const IMAGE_CANDIDATE_PAGE_SIZE = 6;

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
  const [previewInputImage, setPreviewInputImage] = useState<PosterImageCandidate | null>(null);
  const [previewPosterZoomed, setPreviewPosterZoomed] = useState(false);
  const [previewInputImageZoomed, setPreviewInputImageZoomed] = useState(false);
  const [detailRunId, setDetailRunId] = useState<string | null>(null);
  const [deletingPosterIds, setDeletingPosterIds] = useState<string[]>([]);
  const [selectedInputImages, setSelectedInputImages] = useState<string[]>([]);
  const [imageCandidateLimit, setImageCandidateLimit] = useState(IMAGE_CANDIDATE_PAGE_SIZE);
  const [expandedSections, setExpandedSections] = useState<PosterIncludedSection[]>([]);

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
      const selectableRunEntries = runSelectionEntriesForPoster(nextRuns);
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
        if (current && selectableRunEntries.some((entry) => entry.run.id === current)) return current;
        return selectableRunEntries[0]?.run.id ?? null;
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

  const selectableRunEntries = useMemo(
    () => runSelectionEntriesForPoster(runs),
    [runs]
  );

  useEffect(() => {
    setSelectedProductId((current) => {
      if (current && productOptions.some((product) => product.id === current)) return current;
      return productOptions[0]?.id ?? null;
    });
  }, [productOptions]);

  const imageCandidates = useMemo(() => {
    return selectedRun && selectedProductId
      ? productImageCandidatesForRun(selectedRun, selectedProductId)
      : [];
  }, [selectedRun, selectedProductId]);

  // Reset image selection when product changes
  useEffect(() => {
    setSelectedInputImages([]);
    setImageCandidateLimit(IMAGE_CANDIDATE_PAGE_SIZE);
  }, [selectedProductId, selectedRunId]);

  const selectedProduct = productOptions.find((product) => product.id === selectedProductId) ?? null;
  const selectedProductRecord = useMemo(() => {
    if (!selectedRun?.final_output || !selectedProductId) return null;
    return recordsFromUnknown(selectedRun.final_output["products"]).find(
      (product) => String(product.id ?? "") === selectedProductId
    ) ?? null;
  }, [selectedRun, selectedProductId]);
  const selectedMarketingRecord = useMemo(() => {
    if (!selectedRun?.final_output || !selectedProductId) return null;
    return recordsFromUnknown(selectedRun.final_output["marketing_assets"]).find(
      (asset) => String(asset.product_id ?? "") === selectedProductId
    ) ?? null;
  }, [selectedRun, selectedProductId]);
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
        input_images: selectedInputImages.length > 0 ? selectedInputImages : undefined,
      });
      setPosters((current) => [poster, ...current.filter((item) => item.id !== poster.id)]);
      notifications.show({
        title: "포스터 생성 시작",
        message: "포스터 이미지를 생성 중입니다. 완료되면 목록에 이미지가 표시됩니다.",
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
        message: "저장된 포스터 기록을 삭제했습니다.",
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

  function toggleExpandedSection(section: PosterIncludedSection) {
    setExpandedSections((current) =>
      current.includes(section)
        ? current.filter((item) => item !== section)
        : [...current, section]
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Poster Studio</Title>
          <Text size="sm" c="dimmed">
            생성 이미지는 검토용 이미지입니다. 현재는 정해진 스타일로만 생성할 수 있으며, 자유 커스터마이즈는 후속 단계에서 제공 예정입니다.
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
            <div className={classes.selectionGrid}>
              <RunSelectionTable
                entries={selectableRunEntries}
                selectedRunId={selectedRunId}
                disabled={loading || generating}
                onSelectRun={setSelectedRunId}
              />
              <ProductSelectionTable
                products={productOptions}
                selectedProductId={selectedProductId}
                disabled={!selectedRunId || loading || generating}
                onSelectProduct={setSelectedProductId}
              />
            </div>
            {selectedProduct ? (
              <Text size="sm" c="dimmed" lineClamp={2}>
                {selectedProduct.one_liner || selectedProduct.title}
              </Text>
            ) : null}
          </Stack>
        </Paper>

        <div className={classes.studioContentGrid}>
          <Paper withBorder p="md" className={classes.creationSettingsPanel}>
            <Stack gap="md">
              <Stack gap={6}>
                <Text fw={700} size="sm">포함할 내용</Text>
                {SECTION_ORDER.map((section) => (
                  <SectionOption
                    key={section}
                    section={section}
                    checked={includedSections.includes(section)}
                    expanded={expandedSections.includes(section)}
                    preview={posterSectionPreview(section, selectedProductRecord, selectedMarketingRecord)}
                    disabled={generating}
                    onToggleChecked={(checked) => toggleSection(section, checked)}
                    onToggleExpanded={() => toggleExpandedSection(section)}
                  />
                ))}
              </Stack>

              <Stack gap="sm">
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
                  <Stack gap={2}>
                    <Text size="sm">- 상품 1개당 최대 {maxPostersPerProduct}개까지 저장됩니다.</Text>
                    <Text size="sm">- 현재 선택한 상품은 {selectedProductPosterCount}개를 사용 중입니다.</Text>
                    <Text size="sm">- 크기는 {options?.image_size ?? "1024x1536"} portrait로 고정되어 있습니다.</Text>
                  </Stack>
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
                    이 상품은 포스터 {maxPostersPerProduct}개를 모두 사용 중입니다. 기존 포스터를 삭제하면 하나 더 만들 수 있습니다.
                  </Text>
                ) : null}
                {generating ? (
                  <Text size="sm" c="dimmed">
                    생성 작업을 등록하고 있습니다. 등록 후에는 이 화면을 이동하거나 새로고침해도 계속 진행됩니다.
                  </Text>
                ) : null}
              </Stack>

              <Stack gap={6}>
                <Text fw={700} size="sm">참조 이미지 선택 (최대 3개)</Text>
                <Text size="xs" c="dimmed">
                  선택한 상품과 직접 연결된 근거 이미지를 우선 보여줍니다. 이미지를 누르면 크게 확인할 수 있습니다.
                </Text>

                {imageCandidates.length > 0 ? (
                  <Stack gap="xs">
                    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                      {imageCandidates.slice(0, imageCandidateLimit).map((candidate) => {
                        const url = candidate.image_url;
                        const isSelected = selectedInputImages.includes(candidate.image_url);
                        const isDisabled = !isSelected && selectedInputImages.length >= 3;
                        return (
                          <ReferenceImageCard
                            key={url}
                            candidate={candidate}
                            selected={isSelected}
                            disabled={isDisabled || generating}
                            onPreview={() => setPreviewInputImage(candidate)}
                            onToggle={() => {
                              if (isDisabled) return;
                              setSelectedInputImages((prev) =>
                                isSelected ? prev.filter((u) => u !== url) : [...prev, url]
                              );
                            }}
                          />
                        );
                      })}
                    </SimpleGrid>
                    {imageCandidates.length > imageCandidateLimit ? (
                      <Button
                        size="xs"
                        variant="subtle"
                        onClick={() => setImageCandidateLimit((current) => current + IMAGE_CANDIDATE_PAGE_SIZE)}
                      >
                        더 보기 ({Math.min(imageCandidates.length, imageCandidateLimit + IMAGE_CANDIDATE_PAGE_SIZE)} / {imageCandidates.length})
                      </Button>
                    ) : imageCandidates.length > IMAGE_CANDIDATE_PAGE_SIZE ? (
                      <Button
                        size="xs"
                        variant="subtle"
                        onClick={() => setImageCandidateLimit(IMAGE_CANDIDATE_PAGE_SIZE)}
                      >
                        접기
                      </Button>
                    ) : null}
                  </Stack>
                ) : (
                  <Text size="xs" c="dimmed" fs="italic">
                    선택한 상품에 연결된 이미지 후보를 찾지 못했습니다.
                  </Text>
                )}

                {selectedInputImages.length > 0 ? (
                  <Stack gap={4}>
                    <Text size="xs" fw={600}>선택된 이미지 ({selectedInputImages.length}/3)</Text>
                    {selectedInputImages.map((url) => {
                      const candidate = imageCandidates.find((item) => item.image_url === url);
                      return (
                        <Group key={url} gap="xs" wrap="nowrap">
                          <Text size="xs" lineClamp={1} style={{ flex: 1 }}>
                            {candidate?.title ?? "선택된 이미지"}
                          </Text>
                          <ActionIcon
                            size="xs"
                            variant="subtle"
                            color="red"
                            onClick={() => setSelectedInputImages((prev) => prev.filter((u) => u !== url))}
                          >
                            <IconTrash size={12} />
                          </ActionIcon>
                        </Group>
                      );
                    })}
                  </Stack>
                ) : null}
              </Stack>
            </Stack>
          </Paper>

          <Stack gap="md" className={classes.posterListColumn}>
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
                상단 생성 영역에서 run과 product를 선택한 뒤 포스터를 생성하세요.
              </Text>
            </Paper>
          ) : (
            <div className={classes.posterGrid}>
              {latestPosters.map((poster) => (
                <PosterCard
                  key={poster.id}
                  poster={poster}
                  deleting={deletingPosterIds.includes(poster.id)}
                  onDelete={() => void handleDeletePoster(poster)}
                  onPreview={() => setPreviewPoster(poster)}
                  onOpenRun={() => setDetailRunId(poster.run_id)}
                  styleLabel={posterStyleLabel(poster.style_preset, options)}
                />
              ))}
            </div>
          )}
          </Stack>
        </div>
      </div>

      <Modal
        opened={previewPoster !== null}
        onClose={() => {
          setPreviewPoster(null);
          setPreviewPosterZoomed(false);
        }}
        withCloseButton={false}
        padding={0}
        size="auto"
        centered
        styles={{
          content: { background: "transparent", boxShadow: "none", maxHeight: "none", overflow: "visible" },
          body: { padding: 0, overflow: "visible" },
        }}
      >
        {previewPoster ? (
          <ZoomImage
            src={posterImageSrc(previewPoster)}
            alt={previewPoster.product_title}
            zoomed={previewPosterZoomed}
            onToggleZoom={() => setPreviewPosterZoomed((value) => !value)}
          />
        ) : null}
      </Modal>

      <Modal
        opened={previewInputImage !== null}
        onClose={() => {
          setPreviewInputImage(null);
          setPreviewInputImageZoomed(false);
        }}
        withCloseButton={false}
        padding={0}
        size="auto"
        centered
        styles={{
          content: { background: "transparent", boxShadow: "none", maxHeight: "none", overflow: "visible" },
          body: { padding: 0, overflow: "visible" },
        }}
      >
        {previewInputImage ? (
          <ZoomImage
            src={previewInputImage.image_url}
            alt={previewInputImage.title}
            zoomed={previewInputImageZoomed}
            onToggleZoom={() => setPreviewInputImageZoomed((value) => !value)}
          />
        ) : null}
      </Modal>

      <Drawer
        opened={detailRunId !== null}
        onClose={() => setDetailRunId(null)}
        position="right"
        size="90%"
        title="Run Detail"
        closeOnEscape={false}
      >
        {detailRunId ? (
          <RunDetail
            runId={detailRunId}
            onStatusChanged={() => loadData({ silent: true })}
            relatedRuns={runs}
            onSelectRun={setDetailRunId}
          />
        ) : null}
      </Drawer>
    </Stack>
  );
}

function PosterCard({
  poster,
  deleting,
  onDelete,
  onPreview,
  onOpenRun,
  styleLabel,
}: {
  poster: PosterAsset;
  deleting: boolean;
  onDelete: () => void;
  onPreview: () => void;
  onOpenRun: () => void;
  styleLabel: string;
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
            {poster.status === "failed" ? <Badge variant="light" color="red">failed</Badge> : null}
            <Badge variant="light" color="gray">{styleLabel}</Badge>
          </Group>
          <Text fw={700} lineClamp={2}>{poster.product_title}</Text>
          <Text size="xs" c="dimmed" lineClamp={2}>
            옵션: {includedSections || "선택 없음"}
            {poster.input_images.length > 0 ? ` · 참조 이미지 ${poster.input_images.length}개` : ""}
          </Text>
          <Text size="xs" c="dimmed" lineClamp={1}>
            {poster.run_id}
          </Text>
          <Text size="xs" c="dimmed">
            {formatKstDateTime(poster.created_at)}
          </Text>
        </div>

        <Group gap="xs" wrap="nowrap">
          <Button size="xs" variant="subtle" onClick={onOpenRun}>
            Run Detail
          </Button>
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
      </Stack>
    </Paper>
  );
}

function SectionOption({
  section,
  checked,
  expanded,
  preview,
  disabled,
  onToggleChecked,
  onToggleExpanded,
}: {
  section: PosterIncludedSection;
  checked: boolean;
  expanded: boolean;
  preview: string;
  disabled: boolean;
  onToggleChecked: (checked: boolean) => void;
  onToggleExpanded: () => void;
}) {
  return (
    <Paper withBorder p="xs" className={classes.sectionOption}>
      <Group align="flex-start" wrap="nowrap" gap="xs">
        <Checkbox
          checked={checked}
          onChange={(event) => onToggleChecked(event.currentTarget.checked)}
          disabled={disabled}
          aria-label={POSTER_SECTION_LABELS[section]}
        />
        <Stack gap={3} className={classes.sectionOptionBody}>
          <Group justify="space-between" wrap="nowrap" gap="xs">
            <Text size="sm" fw={600}>{POSTER_SECTION_LABELS[section]}</Text>
            <ActionIcon
              size="sm"
              variant="subtle"
              color="gray"
              onClick={onToggleExpanded}
              aria-label={expanded ? "내용 접기" : "내용 펼치기"}
            >
              {expanded ? <IconChevronUp size={15} /> : <IconChevronDown size={15} />}
            </ActionIcon>
          </Group>
          <Text
            size="xs"
            c="dimmed"
            className={
              expanded
                ? classes.sectionPreviewExpanded
                : `${classes.sectionPreviewText} ${classes.sectionPreviewCollapsed}`
            }
          >
            {preview}
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}

function ReferenceImageCard({
  candidate,
  selected,
  disabled,
  onPreview,
  onToggle,
}: {
  candidate: PosterImageCandidate;
  selected: boolean;
  disabled: boolean;
  onPreview: () => void;
  onToggle: () => void;
}) {
  return (
    <Paper
      withBorder
      p="xs"
      className={`${classes.referenceImageCard} ${selected ? classes.selectedReferenceImageCard : ""}`}
      style={{ opacity: disabled ? 0.5 : 1 }}
    >
      <Stack gap={6}>
        <button
          type="button"
          className={classes.referenceImageButton}
          onClick={onPreview}
          aria-label={`${candidate.title || "참조 이미지 후보"} 크게 보기`}
        >
          <Image
            src={candidate.thumbnail_url || candidate.image_url}
            alt={candidate.title || "참조 이미지 후보"}
            h={118}
            w="100%"
            fit="cover"
            radius="xs"
          />
        </button>
        <Text size="xs" fw={700} lineClamp={2}>
          {candidate.title || "이미지 후보"}
        </Text>
        <Button size="xs" variant={selected ? "filled" : "light"} disabled={disabled} onClick={onToggle}>
          {selected ? "선택 해제" : "선택"}
        </Button>
      </Stack>
    </Paper>
  );
}

function RunSelectionTable({
  entries,
  selectedRunId,
  disabled,
  onSelectRun,
}: {
  entries: RunSelectionEntry[];
  selectedRunId: string | null;
  disabled: boolean;
  onSelectRun: (runId: string) => void;
}) {
  return (
    <Stack gap={6}>
      <Text size="sm" fw={700}>Run 선택</Text>
      <Paper withBorder className={classes.selectionPanel}>
        <ScrollArea h={210}>
          <Table highlightOnHover verticalSpacing="xs" className={classes.selectionTable}>
            <Table.Tbody>
              {entries.length > 0 ? entries.map(({ run, indent }) => {
                const rowClassName = [
                  run.id === selectedRunId ? classes.selectedSelectionRow : classes.selectionRow,
                  indent ? classes.revisionSelectionRow : "",
                ].filter(Boolean).join(" ");
                return (
                  <Table.Tr
                    key={run.id}
                    className={rowClassName}
                    onClick={disabled ? undefined : () => onSelectRun(run.id)}
                  >
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        {indent ? <Text className={classes.branchMarker}>↳</Text> : null}
                        <div className={classes.selectionRunText}>
                          <Text fw={700} size="sm" lineClamp={1}>{getRunTitle(run)}</Text>
                          <Text ff="monospace" size="xs" c="dimmed" lineClamp={1}>{run.id}</Text>
                        </div>
                        {indent ? (
                          <Badge size="xs" variant="light" color="gray">
                            Rev {run.revision_number}
                          </Badge>
                        ) : null}
                      </Group>
                    </Table.Td>
                    <Table.Td className={classes.selectionStatusCell}>
                      <StatusBadge status={run.status} />
                    </Table.Td>
                    <Table.Td className={classes.selectionCountCell}>
                      <Text size="xs" c="dimmed">{productOptionsForRun(run).length}개</Text>
                    </Table.Td>
                  </Table.Tr>
                );
              }) : (
                <Table.Tr>
                  <Table.Td>
                    <Text size="sm" c="dimmed">상품이 있는 run이 없습니다.</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Paper>
    </Stack>
  );
}

function ProductSelectionTable({
  products,
  selectedProductId,
  disabled,
  onSelectProduct,
}: {
  products: ProductOption[];
  selectedProductId: string | null;
  disabled: boolean;
  onSelectProduct: (productId: string) => void;
}) {
  return (
    <Stack gap={6}>
      <Text size="sm" fw={700}>Product 선택</Text>
      <Paper withBorder className={classes.selectionPanel}>
        <ScrollArea h={210}>
          <Table highlightOnHover verticalSpacing="xs" className={classes.selectionTable}>
            <Table.Tbody>
              {products.length > 0 ? products.map((product, index) => (
                <Table.Tr
                  key={product.id}
                  className={product.id === selectedProductId ? classes.selectedSelectionRow : classes.selectionRow}
                  onClick={disabled ? undefined : () => onSelectProduct(product.id)}
                >
                  <Table.Td className={classes.selectionIndexCell}>
                    <Badge size="xs" variant="light" color="gray">{index + 1}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text fw={700} size="sm" lineClamp={1}>{product.title}</Text>
                    <Text size="xs" c="dimmed" lineClamp={1}>{product.one_liner || product.id}</Text>
                  </Table.Td>
                </Table.Tr>
              )) : (
                <Table.Tr>
                  <Table.Td>
                    <Text size="sm" c="dimmed">선택한 run에 상품이 없습니다.</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Paper>
    </Stack>
  );
}

function ZoomImage({
  src,
  alt,
  zoomed,
  onToggleZoom,
}: {
  src: string;
  alt: string;
  zoomed: boolean;
  onToggleZoom: () => void;
}) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragStartRef = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);
  const draggedRef = useRef(false);

  useEffect(() => {
    setOffset({ x: 0, y: 0 });
    dragStartRef.current = null;
    draggedRef.current = false;
  }, [src, zoomed]);

  function handleClick() {
    if (draggedRef.current) {
      draggedRef.current = false;
      return;
    }
    if (zoomed) {
      setOffset({ x: 0, y: 0 });
    }
    onToggleZoom();
  }

  function handlePointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (!zoomed) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      offsetX: offset.x,
      offsetY: offset.y,
    };
    draggedRef.current = false;
  }

  function handlePointerMove(event: PointerEvent<HTMLButtonElement>) {
    if (!zoomed || !dragStartRef.current) return;
    event.preventDefault();
    const dx = event.clientX - dragStartRef.current.x;
    const dy = event.clientY - dragStartRef.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) {
      draggedRef.current = true;
    }
    setOffset({
      x: dragStartRef.current.offsetX + dx,
      y: dragStartRef.current.offsetY + dy,
    });
  }

  function handlePointerEnd(event: PointerEvent<HTMLButtonElement>) {
    if (!dragStartRef.current) return;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture may already be released by the browser.
    }
    dragStartRef.current = null;
  }

  const transform = zoomed ? `translate3d(${offset.x}px, ${offset.y}px, 0) scale(1.5)` : undefined;

  return (
    <div className={classes.zoomPreviewFrame} onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`${classes.zoomPreviewButton} ${zoomed ? classes.zoomed : ""}`}
        style={{ transform }}
        onClick={handleClick}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
        aria-label={zoomed ? "이미지 축소" : "이미지 확대"}
      >
        <img src={src} alt={alt} className={classes.zoomPreviewImage} />
        <span className={classes.zoomIcon}>
          {zoomed ? <IconZoomOut size={22} /> : <IconZoomIn size={22} />}
        </span>
      </button>
    </div>
  );
}

function runSelectionEntriesForPoster(runs: WorkflowRun[]): RunSelectionEntry[] {
  const runsById = new Map(runs.map((run) => [run.id, run]));
  const revisionsByParentId = new Map<string, WorkflowRun[]>();
  const orphanRevisions: WorkflowRun[] = [];

  runs.forEach((run) => {
    if (!run.parent_run_id) return;
    if (!runsById.has(run.parent_run_id)) {
      orphanRevisions.push(run);
      return;
    }
    const revisions = revisionsByParentId.get(run.parent_run_id) ?? [];
    revisions.push(run);
    revisionsByParentId.set(run.parent_run_id, revisions);
  });

  const entries: RunSelectionEntry[] = [];
  sortRunsByNewestCreated(runs.filter((run) => !run.parent_run_id)).forEach((rootRun) => {
    const rootHasProducts = runHasProducts(rootRun);
    if (rootHasProducts) {
      entries.push({ run: rootRun, indent: false });
    }

    sortRevisionsByNewestRevision(revisionsByParentId.get(rootRun.id) ?? [])
      .filter(runHasProducts)
      .forEach((revision) => {
        entries.push({ run: revision, indent: rootHasProducts });
      });
  });

  sortRunsByNewestCreated(orphanRevisions)
    .filter(runHasProducts)
    .forEach((run) => entries.push({ run, indent: false }));

  return entries;
}

function runHasProducts(run: WorkflowRun) {
  return productOptionsForRun(run).length > 0;
}

function sortRevisionsByNewestRevision(runs: WorkflowRun[]) {
  return runs.slice().sort((a, b) =>
    (b.revision_number ?? 0) - (a.revision_number ?? 0) ||
    runCreatedAtTime(b) - runCreatedAtTime(a)
  );
}

function sortRunsByNewestCreated(runs: WorkflowRun[]) {
  return runs.slice().sort((a, b) => runCreatedAtTime(b) - runCreatedAtTime(a));
}

function runCreatedAtTime(run: WorkflowRun) {
  const timestamp = new Date(run.created_at).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function productImageCandidatesForRun(run: WorkflowRun, productId: string): PosterImageCandidate[] {
  const finalOutput = run.final_output;
  if (!finalOutput) return [];

  const products = recordsFromUnknown(finalOutput["products"]);
  const product = products.find((item) => String(item.id ?? "") === productId);
  if (!product) return [];

  const productSourceIds = stringListFromUnknown(product.source_ids);
  const sourceIds = new Set(productSourceIds);
  const sourceOrder = new Map(productSourceIds.map((sourceId, index) => [sourceId, index]));
  const docs = recordsFromUnknown(finalOutput["retrieved_documents"]);
  const linkedContentIds = new Set(
    docs
      .filter((doc) => sourceIds.has(String(doc.doc_id ?? "")))
      .map((doc) => recordFromUnknown(doc.metadata).content_id)
      .map((value) => String(value ?? "").trim())
      .filter(Boolean)
  );

  const candidates: PosterImageCandidate[] = [];
  const seen = new Set<string>();
  const addCandidate = (
    url: unknown,
    {
      thumbnailUrl,
      title,
      source,
      relevanceLabel,
      relevanceRank,
    }: {
      thumbnailUrl?: unknown;
      title: string;
      source: string;
      relevanceLabel: string;
      relevanceRank: number;
    }
  ) => {
    if (typeof url !== "string") return;
    const normalized = url.trim();
    if (!normalized.startsWith("http") || seen.has(normalized)) return;
    seen.add(normalized);
    candidates.push({
      image_url: normalized,
      thumbnail_url: typeof thumbnailUrl === "string" && thumbnailUrl.trim() ? thumbnailUrl.trim() : normalized,
      title,
      source,
      relevance_label: relevanceLabel,
      relevance_rank: relevanceRank,
    });
  };

  docs.forEach((doc, index) => {
    const metadata = recordFromUnknown(doc.metadata);
    const docId = String(doc.doc_id ?? "");
    const contentId = String(metadata.content_id ?? "").trim();
    const isDirect = sourceIds.has(docId);
    const isLinked = Boolean(contentId && linkedContentIds.has(contentId));
    if (!isDirect && !isLinked) {
      return;
    }
    const title = String(doc.title || metadata.title || metadata.name || "이미지 후보");
    const source = String(metadata.source_family || metadata.source || "근거 이미지");
    const relevanceLabel = isDirect ? "상품 직접 근거" : "같은 장소 후보";
    const relevanceRank = isDirect ? sourceOrder.get(docId) ?? index : 100 + index;
    addCandidate(doc.image_url, {
      title,
      source,
      relevanceLabel,
      relevanceRank,
    });
    addCandidate(metadata.image_url, {
      title,
      source,
      relevanceLabel,
      relevanceRank,
    });
    addCandidate(metadata.firstimage, {
      title,
      source,
      relevanceLabel,
      relevanceRank,
    });
    addCandidate(metadata.firstimage2, {
      title: `${title} 추가 이미지`,
      source,
      relevanceLabel,
      relevanceRank: relevanceRank + 0.1,
    });
    const imageCandidates = parseMetadataJson(metadata.image_candidates);
    recordsFromUnknown(imageCandidates).forEach((candidate) => {
      addCandidate(candidate.image_url, {
        thumbnailUrl: candidate.thumbnail_url,
        title: String(candidate.title || title),
        source: String(candidate.source || source),
        relevanceLabel,
        relevanceRank: relevanceRank + 0.2,
      });
    });
  });

  return candidates.sort((a, b) => a.relevance_rank - b.relevance_rank || a.title.localeCompare(b.title));
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

function getRunTitle(run: WorkflowRun) {
  const products = Array.isArray(run.final_output?.products)
    ? (run.final_output.products as Array<{ title?: unknown }>)
    : [];
  const productTitle = products.find((product) => typeof product.title === "string")?.title;
  if (typeof productTitle === "string" && productTitle.trim()) {
    return productTitle;
  }
  return run.input.message || `${run.input.region ?? "Region"} product planning`;
}

const POSTER_STYLE_LABEL_FALLBACK: Record<string, string> = {
  editorial_travel: "프리미엄 여행 매거진",
  night_city: "야간 도시 시네마틱",
  minimal_event: "미니멀 홍보 포스터",
};

function posterStyleLabel(styleId: string, options: PosterOptions | null) {
  return (
    options?.style_presets.find((preset) => preset.id === styleId)?.label ??
    POSTER_STYLE_LABEL_FALLBACK[styleId] ??
    styleId
  );
}

function posterSectionPreview(
  section: PosterIncludedSection,
  product: Record<string, unknown> | null,
  marketing: Record<string, unknown> | null
) {
  if (!product) return "상품을 선택하면 이 항목에 들어갈 실제 내용이 표시됩니다.";
  const salesCopy = recordFromUnknown(marketing?.sales_copy);
  if (section === "product_summary") {
    return [product.title, product.one_liner, stringListFromUnknown(product.core_value).join(", ")]
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join(" / ") || "상품 요약 없음";
  }
  if (section === "itinerary") {
    const items = recordsFromUnknown(product.itinerary)
      .map((item) => String(item.name || item.title || item.place || item.activity || item.description || "").trim())
      .filter(Boolean);
    return items.join(" → ") || "일정/경험 요소 없음";
  }
  if (section === "marketing_copy") {
    return [salesCopy.headline, salesCopy.subheadline]
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join(" / ") || "마케팅 문구 없음";
  }
  if (section === "sns_copy") {
    return stringListFromUnknown(marketing?.sns_posts)[0] || "SNS 문구 없음";
  }
  if (section === "evidence_summary") {
    return String(product.evidence_summary || "").trim() || "근거 요약 없음";
  }
  if (section === "claim_limits") {
    const limits = [
      ...stringListFromUnknown(product.claim_limits),
      ...stringListFromUnknown(product.not_to_claim),
      ...stringListFromUnknown(product.needs_review),
    ];
    return limits.join(" / ") || "제한/주의사항 없음";
  }
  return "선택한 데이터가 포스터 프롬프트에 반영됩니다.";
}

function recordsFromUnknown(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    : [];
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function stringListFromUnknown(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function parseMetadataJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
