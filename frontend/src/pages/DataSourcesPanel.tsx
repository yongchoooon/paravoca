import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Drawer,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconApi,
  IconDatabase,
  IconEye,
  IconFileSearch,
  IconMap2,
  IconRefresh,
  IconSearch,
} from "@tabler/icons-react";
import {
  DataSourceClassificationCatalogItem,
  DataSourceCatalogBrowserResponse,
  DataSourceDocumentBrowserResponse,
  DataSourceDocumentPreview,
  DataSourceOverview,
  DataSourceOverviewItem,
  DataSourceRegionCatalogItem,
  DataSourceTourismItemBrowserResponse,
  DataSourceTourismItemPreview,
  getDataSourceCatalogs,
  getDataSourceDocuments,
  getDataSourceOverview,
  getDataSourceTourismItems,
} from "../services/dataSourcesApi";
import { formatKstDateTime } from "../utils/datetime";
import classes from "./DataSourcesPanel.module.css";

type StatusTone = "green" | "blue" | "yellow" | "gray" | "red" | "teal";

const CATEGORY_LABELS: Record<string, string> = {
  core_tourism: "기본 관광정보",
  visual: "사진/시각 자료",
  theme: "테마 보강",
  route: "동선 자료",
  story: "해설/스토리",
  signal: "수요/혼잡 신호",
  web_evidence: "공식 웹 근거",
};

const PURPOSE_LABELS: Record<string, string> = {
  all: "전체 데이터",
  base: "기본 관광 상품",
  event: "행사/축제",
  visual: "이미지/포스터",
  pet: "반려동물",
  walking: "도보/트레킹",
  wellness: "웰니스/힐링",
  demand: "혼잡/수요 판단",
  culture: "문화해설/스토리",
};

const GAP_LABELS: Record<string, string> = {
  missing_detail_info: "이용 시간/요금/주차",
  missing_image_asset: "대표/상세 이미지",
  missing_operating_hours: "운영 시간",
  missing_price_or_fee: "요금 정보",
  missing_booking_info: "예약 정보",
  missing_related_places: "주변 코스",
  missing_pet_policy: "반려동물 조건",
  missing_visual_reference: "포스터 참고 이미지",
  missing_theme_specific_data: "테마 속성",
  missing_wellness_attributes: "웰니스 속성",
  missing_medical_context: "의료관광 검수",
  missing_route_context: "동선 판단",
  missing_route_asset: "코스/GPX",
  missing_story_asset: "해설/스토리",
  missing_multilingual_story: "다국어 스토리",
  missing_sustainability_context: "생태/공정관광",
  missing_demand_signal: "수요 신호",
  missing_crowding_signal: "혼잡 신호",
  missing_regional_demand_signal: "지역 수요",
  missing_user_business_info: "운영자 확인 정보",
};

export function DataSourcesPanel() {
  const [overview, setOverview] = useState<DataSourceOverview | null>(null);
  const [documents, setDocuments] = useState<DataSourceDocumentBrowserResponse | null>(null);
  const [tourismItems, setTourismItems] = useState<DataSourceTourismItemBrowserResponse | null>(null);
  const [catalogs, setCatalogs] = useState<DataSourceCatalogBrowserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [catalogsLoading, setCatalogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>("apis");
  const [purpose, setPurpose] = useState<string | null>("all");
  const [apiQuery, setApiQuery] = useState("");
  const [apiCategory, setApiCategory] = useState<string | null>("all");
  const [apiStatus, setApiStatus] = useState<string | null>("all");
  const [documentSearchInput, setDocumentSearchInput] = useState("");
  const [documentQuery, setDocumentQuery] = useState("");
  const [documentSource, setDocumentSource] = useState<string | null>("all");
  const [documentStatus, setDocumentStatus] = useState<string | null>("all");
  const [itemSearchInput, setItemSearchInput] = useState("");
  const [itemQuery, setItemQuery] = useState("");
  const [itemSource, setItemSource] = useState<string | null>("all");
  const [itemContentType, setItemContentType] = useState<string | null>("all");
  const [itemImageFilter, setItemImageFilter] = useState<string | null>("all");
  const [regionSearchInput, setRegionSearchInput] = useState("");
  const [regionQuery, setRegionQuery] = useState("");
  const [classificationSearchInput, setClassificationSearchInput] = useState("");
  const [classificationQuery, setClassificationQuery] = useState("");
  const [selectedRegionCode, setSelectedRegionCode] = useState<string | null>(null);
  const [selectedClassLevel1, setSelectedClassLevel1] = useState<string | null>(null);
  const [selectedClassLevel2, setSelectedClassLevel2] = useState<string | null>(null);
  const [regionOffset, setRegionOffset] = useState(0);
  const [regionChildOffset, setRegionChildOffset] = useState(0);
  const [regionSearchOffset, setRegionSearchOffset] = useState(0);
  const [classificationOffset, setClassificationOffset] = useState(0);
  const [classificationLevel2Offset, setClassificationLevel2Offset] = useState(0);
  const [classificationLevel3Offset, setClassificationLevel3Offset] = useState(0);
  const [classificationSearchOffset, setClassificationSearchOffset] = useState(0);
  const [regionChildrenCatalogs, setRegionChildrenCatalogs] = useState<DataSourceCatalogBrowserResponse | null>(null);
  const [regionSearchCatalogs, setRegionSearchCatalogs] = useState<DataSourceCatalogBrowserResponse | null>(null);
  const [classificationLevel2Catalogs, setClassificationLevel2Catalogs] = useState<DataSourceCatalogBrowserResponse | null>(null);
  const [classificationLevel3Catalogs, setClassificationLevel3Catalogs] = useState<DataSourceCatalogBrowserResponse | null>(null);
  const [classificationSearchCatalogs, setClassificationSearchCatalogs] = useState<DataSourceCatalogBrowserResponse | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<DataSourceDocumentPreview | null>(null);
  const [selectedItem, setSelectedItem] = useState<DataSourceTourismItemPreview | null>(null);

  async function loadOverview(options: { silent?: boolean } = {}) {
    try {
      if (options.silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      setOverview(await getDataSourceOverview());
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터 소스 상태를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function loadDocuments() {
    try {
      setDocumentsLoading(true);
      setDocuments(await getDataSourceDocuments({
        keyword: documentQuery,
        source_family: documentSource ?? "all",
        embedding_status: documentStatus ?? "all",
        limit: 40,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI 참고 자료를 불러오지 못했습니다.");
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function loadTourismItems() {
    try {
      setItemsLoading(true);
      setTourismItems(await getDataSourceTourismItems({
        keyword: itemQuery,
        source_family: itemSource ?? "all",
        content_type: itemContentType ?? "all",
        has_image: itemImageFilter === "with" ? true : itemImageFilter === "without" ? false : null,
        limit: 40,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "실제 수집 데이터를 불러오지 못했습니다.");
    } finally {
      setItemsLoading(false);
    }
  }

  async function loadCatalogs() {
    try {
      setCatalogsLoading(true);
      const [
        rootCatalogs,
        regionChildCatalogs,
        regionSearchResults,
        classificationLevel2Results,
        classificationLevel3Results,
        classificationSearchResults,
      ] = await Promise.all([
        getDataSourceCatalogs({
          region_offset: regionOffset,
          classification_offset: classificationOffset,
          limit: 30,
        }),
        selectedRegionCode
          ? getDataSourceCatalogs({
            region_code: selectedRegionCode,
            region_offset: regionChildOffset,
            limit: 30,
          })
          : Promise.resolve(null),
        regionQuery
          ? getDataSourceCatalogs({
            region_keyword: regionQuery,
            region_offset: regionSearchOffset,
            limit: 30,
          })
          : Promise.resolve(null),
        selectedClassLevel1
          ? getDataSourceCatalogs({
            lcls_systm_1: selectedClassLevel1,
            classification_offset: classificationLevel2Offset,
            limit: 30,
          })
          : Promise.resolve(null),
        selectedClassLevel1 && selectedClassLevel2
          ? getDataSourceCatalogs({
            lcls_systm_1: selectedClassLevel1,
            lcls_systm_2: selectedClassLevel2,
            classification_offset: classificationLevel3Offset,
            limit: 30,
          })
          : Promise.resolve(null),
        classificationQuery
          ? getDataSourceCatalogs({
            classification_keyword: classificationQuery,
            classification_offset: classificationSearchOffset,
            limit: 30,
          })
          : Promise.resolve(null),
      ]);
      setCatalogs(rootCatalogs);
      setRegionChildrenCatalogs(regionChildCatalogs);
      setRegionSearchCatalogs(regionSearchResults);
      setClassificationLevel2Catalogs(classificationLevel2Results);
      setClassificationLevel3Catalogs(classificationLevel3Results);
      setClassificationSearchCatalogs(classificationSearchResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "지역/분류 기준표를 불러오지 못했습니다.");
    } finally {
      setCatalogsLoading(false);
    }
  }

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    void loadCatalogs();
  }, [
    regionQuery,
    classificationQuery,
    selectedRegionCode,
    selectedClassLevel1,
    selectedClassLevel2,
    regionOffset,
    regionChildOffset,
    regionSearchOffset,
    classificationOffset,
    classificationLevel2Offset,
    classificationLevel3Offset,
    classificationSearchOffset,
  ]);

  useEffect(() => {
    void loadDocuments();
  }, [documentQuery, documentSource, documentStatus]);

  useEffect(() => {
    void loadTourismItems();
  }, [itemQuery, itemSource, itemContentType, itemImageFilter]);

  const selectedSource = useMemo(
    () => overview?.sources.find((source) => source.source_family === selectedSourceId) ?? null,
    [overview?.sources, selectedSourceId]
  );

  const sourceOptions = useMemo(() => {
    return [
      { value: "all", label: "전체 API" },
      ...(overview?.sources ?? []).map((source) => ({
        value: source.source_family,
        label: cleanDisplayName(source.display_name),
      })),
    ];
  }, [overview?.sources]);

  const categoryOptions = useMemo(() => {
    const categories = Array.from(new Set((overview?.sources ?? []).map((source) => source.category)));
    return [
      { value: "all", label: "전체 역할" },
      ...categories.map((value) => ({ value, label: categoryLabel(value) })),
    ];
  }, [overview?.sources]);

  const purposeOptions = useMemo(() => {
    const profiles = overview?.purpose_profiles?.length ? overview.purpose_profiles : [{ key: "all", label: "전체 데이터" }];
    return profiles.map((profile) => ({ value: profile.key, label: profile.label }));
  }, [overview?.purpose_profiles]);

  const visibleSources = useMemo(() => {
    const normalizedQuery = apiQuery.trim().toLowerCase();
    return [...(overview?.sources ?? [])]
      .filter((source) => {
        const matchesQuery =
          normalizedQuery.length === 0 ||
          cleanDisplayName(source.display_name).toLowerCase().includes(normalizedQuery) ||
          source.purpose.toLowerCase().includes(normalizedQuery) ||
          source.input_fields.join(" ").toLowerCase().includes(normalizedQuery) ||
          source.output_fields.join(" ").toLowerCase().includes(normalizedQuery);
        const matchesCategory = !apiCategory || apiCategory === "all" || source.category === apiCategory;
        const matchesStatus = !apiStatus || apiStatus === "all" || source.readiness_status === apiStatus;
        return matchesQuery && matchesCategory && matchesStatus;
      })
      .sort((a, b) => relevanceScore(b, purpose) - relevanceScore(a, purpose));
  }, [apiCategory, apiQuery, apiStatus, overview?.sources, purpose]);

  const contentTypeOptions = useMemo(() => {
    const counts = overview?.tourism_inventory.content_type_counts ?? {};
    return [
      { value: "all", label: "전체 유형" },
      ...Object.keys(counts).map((contentType) => ({ value: contentType, label: contentTypeLabel(contentType) })),
    ];
  }, [overview?.tourism_inventory.content_type_counts]);

  if (loading) {
    return (
      <Paper withBorder p="lg">
        <Group gap="sm">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">데이터 카탈로그를 불러오는 중입니다.</Text>
        </Group>
      </Paper>
    );
  }

  if (!overview) {
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />}>
        {error ?? "데이터 카탈로그를 불러오지 못했습니다."}
      </Alert>
    );
  }

  return (
    <Stack gap="md">
      {error ? (
        <Alert color="red" icon={<IconAlertCircle size={16} />}>
          {error}
        </Alert>
      ) : null}

      <Paper withBorder p="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Group gap="xs" mb={4}>
              <Text fw={700}>Data Sources</Text>
              <Badge variant="light" color="blue">운영자용 데이터 카탈로그</Badge>
            </Group>
            <Title order={3}>{overview.purpose}</Title>
            <Text size="sm" c="dimmed" maw={980}>
              {overview.purpose_detail}
            </Text>
          </div>
          <Button
            variant="light"
            leftSection={<IconRefresh size={16} />}
            loading={refreshing}
            onClick={() => void loadOverview({ silent: true })}
          >
            새로고침
          </Button>
        </Group>
      </Paper>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} className={classes.metricGrid}>
        <SummaryCard
          label="연결된 데이터 API"
          value={`${overview.summary.ready_sources}/${overview.summary.total_sources}`}
          description="현재 시스템에서 호출할 수 있는 데이터 연결입니다. 실제 저장된 데이터 수와는 다릅니다."
          icon={<IconApi size={18} />}
        />
        <SummaryCard
          label="실제 저장된 관광 데이터"
          value={formatNumber(overview.summary.tourism_item_count)}
          description={`${formatNumber(overview.tourism_inventory.items_with_image)}개는 대표 이미지가 있습니다.`}
          icon={<IconDatabase size={18} />}
        />
        <SummaryCard
          label="RAG 검색 근거 자료"
          value={formatNumber(overview.summary.source_document_count)}
          description={`${formatNumber(overview.summary.indexed_document_count)}개가 RAG/AI 검색 가능한 상태입니다.`}
          icon={<IconFileSearch size={18} />}
        />
        <SummaryCard
          label="지역/분류 기준표"
          value={formatNumber(overview.catalogs.reduce((sum, catalog) => sum + catalog.record_count, 0))}
          description="지역과 관광 분류를 숫자가 아니라 실제 목록으로 탐색합니다."
          icon={<IconMap2 size={18} />}
        />
      </SimpleGrid>

      <Paper withBorder p="md" className={classes.flowPanel}>
        <Text fw={700} size="sm">AI 참고 자료가 쌓이고 쓰이는 방식</Text>
        <Group gap="xs" mt="sm" className={classes.flowSteps}>
          {["외부 관광 API 호출", "관광 데이터 DB 저장", "AI가 읽기 좋은 문서로 변환", "검색 준비 상태 확인", "상품 설명/추천/일정 구성 때 참고"].map((step, index) => (
            <Group key={step} gap="xs" wrap="nowrap" className={classes.flowStep}>
              <Badge variant="filled" color="gray">{index + 1}</Badge>
              <Text size="sm" fw={600}>{step}</Text>
            </Group>
          ))}
        </Group>
      </Paper>

      <Tabs value={activeTab} onChange={setActiveTab} className={classes.catalogTabs}>
        <Tabs.List>
          <Tabs.Tab value="apis">데이터 API</Tabs.Tab>
          <Tabs.Tab value="items">실제 수집 데이터</Tabs.Tab>
          <Tabs.Tab value="documents">AI 검색 근거 자료</Tabs.Tab>
          <Tabs.Tab value="catalogs">지역/분류</Tabs.Tab>
          <Tabs.Tab value="purpose">목적별 보기</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="apis" pt="md">
          <Stack gap="md">
            <PanelHeader
              title="데이터 API"
              description="각 API가 어떤 입력을 받아 어떤 데이터를 돌려주는지 확인합니다. 목적을 선택하면 관련 API가 위로 올라오지만, 전체 API는 계속 보입니다."
            />
            <FilterBar>
              <TextInput
                leftSection={<IconSearch size={15} />}
                placeholder="API 이름, 입력값, 출력값 검색"
                value={apiQuery}
                onChange={(event) => setApiQuery(event.currentTarget.value)}
              />
              <Select data={purposeOptions} value={purpose} onChange={setPurpose} w={190} />
              <Select data={categoryOptions} value={apiCategory} onChange={setApiCategory} w={170} />
              <Select data={statusOptions()} value={apiStatus} onChange={setApiStatus} w={170} />
            </FilterBar>
            <Paper withBorder>
              <ScrollArea>
                <Table striped highlightOnHover verticalSpacing="sm" className={classes.apiTable}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th className={classes.apiNameColumn}>API</Table.Th>
                      <Table.Th className={classes.apiPurposeColumn}>어디에 쓰이나</Table.Th>
                      <Table.Th className={classes.apiFieldColumn}>입력값</Table.Th>
                      <Table.Th className={classes.apiFieldColumn}>출력값</Table.Th>
                      <Table.Th className={classes.apiStatusColumn}>상태</Table.Th>
                      <Table.Th className={classes.apiInventoryColumn}>저장/근거</Table.Th>
                      <Table.Th className={classes.apiActionColumn}>상세</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {visibleSources.length > 0 ? (
                      visibleSources.map((source) => (
                        <Table.Tr key={source.source_family}>
                          <Table.Td>
                            <Text fw={700} size="sm" lineClamp={1}>{cleanDisplayName(source.display_name)}</Text>
                            <Group gap={6} mt={4}>
                              <Badge size="xs" variant="light" color="gray">{categoryLabel(source.category)}</Badge>
                              {relevanceScore(source, purpose) > 0 ? (
                                <Badge size="xs" variant="light" color="teal">{purposeLabel(purpose)} 관련</Badge>
                              ) : null}
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm" lineClamp={3}>{source.purpose}</Text>
                          </Table.Td>
                          <Table.Td>
                            <FieldPreview fields={source.input_fields} />
                          </Table.Td>
                          <Table.Td>
                            <FieldPreview fields={source.output_fields} />
                          </Table.Td>
                          <Table.Td>
                            <Badge variant="light" color={readinessTone(source.readiness_status)}>
                              {source.status_label}
                            </Badge>
                            <Text size="xs" c="dimmed" mt={4} lineClamp={2}>{source.status_detail}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm" fw={700}>{formatNumber(source.stored_count)}개</Text>
                            <Text size="xs" c="dimmed">AI 근거 {formatNumber(source.evidence_count)}개</Text>
                          </Table.Td>
                          <Table.Td>
                            <Button
                              size="compact-xs"
                              variant="subtle"
                              leftSection={<IconEye size={14} />}
                              onClick={() => setSelectedSourceId(source.source_family)}
                            >
                              보기
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={7} text="조건에 맞는 데이터 API가 없습니다." />
                    )}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            </Paper>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="items" pt="md">
          <Stack gap="md">
            <PanelHeader
              title="실제 수집 데이터"
              description="API 연결 상태가 아니라 DB에 실제로 저장된 관광지, 행사, 숙박, 이미지 보유 여부를 확인합니다."
            />
            <FilterBar>
              <TextInput
                leftSection={<IconSearch size={15} />}
                placeholder="관광지명, 주소, contentId 입력 후 Enter"
                value={itemSearchInput}
                onChange={(event) => setItemSearchInput(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setItemQuery(itemSearchInput.trim());
                }}
              />
              <Button variant="light" leftSection={<IconSearch size={15} />} onClick={() => setItemQuery(itemSearchInput.trim())}>
                검색
              </Button>
              <Select data={sourceOptions} value={itemSource} onChange={setItemSource} w={210} />
              <Select data={contentTypeOptions} value={itemContentType} onChange={setItemContentType} w={150} />
              <Select
                data={[
                  { value: "all", label: "이미지 전체" },
                  { value: "with", label: "이미지 있음" },
                  { value: "without", label: "이미지 없음" },
                ]}
                value={itemImageFilter}
                onChange={setItemImageFilter}
                w={150}
              />
            </FilterBar>
            <Paper withBorder>
              <ResultHeader loading={itemsLoading} total={tourismItems?.total ?? 0} limit={tourismItems?.limit ?? 0} />
              <ScrollArea>
                <Table striped highlightOnHover verticalSpacing="sm" className={classes.itemTable}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>관광 데이터</Table.Th>
                      <Table.Th>출처/유형</Table.Th>
                      <Table.Th>지역/분류</Table.Th>
                      <Table.Th>보유 상태</Table.Th>
                      <Table.Th>수집 출처</Table.Th>
                      <Table.Th>상세</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(tourismItems?.items ?? []).length > 0 ? (
                      tourismItems!.items.map((item) => (
                        <Table.Tr key={item.id}>
                          <Table.Td>
                            <Text fw={700} size="sm" lineClamp={1}>{item.title}</Text>
                            <Text size="xs" c="dimmed" lineClamp={1}>{item.address ?? "주소 정보 없음"}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm" fw={600}>{item.source_label}</Text>
                            <Badge size="xs" variant="light" color="gray">{item.content_type_label}</Badge>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" lineClamp={1}>{item.ldong_label ?? "지역 기준표 미연결"}</Text>
                            <Text size="xs" c="dimmed" lineClamp={1}>{item.classification_label ?? "관광 분류 미연결"}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Group gap={6}>
                              <Badge size="xs" color={item.has_image ? "green" : "yellow"} variant="light">
                                {item.has_image ? "이미지 있음" : "이미지 없음"}
                              </Badge>
                              <Badge size="xs" color={item.has_ai_evidence ? "green" : "gray"} variant="light">
                                {item.has_ai_evidence ? "AI 근거 있음" : "AI 근거 없음"}
                              </Badge>
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" lineClamp={2}>{item.origin_summary}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Button size="compact-xs" variant="subtle" onClick={() => setSelectedItem(item)}>
                              보기
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={6} text="조건에 맞는 실제 수집 데이터가 없습니다." />
                    )}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            </Paper>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="documents" pt="md">
          <Stack gap="md">
            <PanelHeader
              title="AI 검색 근거 자료"
              description="원본 API 응답을 AI가 검색하기 쉬운 짧은 문서로 바꾼 자료입니다. 검색 준비 상태가 완료되어야 상품 설명, 추천 이유, 일정 구성에서 AI가 찾을 수 있습니다."
            />
            <FilterBar>
              <TextInput
                leftSection={<IconSearch size={15} />}
                placeholder="제주, 반려동물, 축제, 오름 입력 후 Enter"
                value={documentSearchInput}
                onChange={(event) => setDocumentSearchInput(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setDocumentQuery(documentSearchInput.trim());
                }}
              />
              <Button variant="light" leftSection={<IconSearch size={15} />} onClick={() => setDocumentQuery(documentSearchInput.trim())}>
                검색
              </Button>
              <Select data={sourceOptions} value={documentSource} onChange={setDocumentSource} w={210} />
              <Select data={documentStatusOptions()} value={documentStatus} onChange={setDocumentStatus} w={170} />
            </FilterBar>
            <Paper withBorder>
              <ResultHeader loading={documentsLoading} total={documents?.total ?? 0} limit={documents?.limit ?? 0} />
              <ScrollArea>
                <Table striped highlightOnHover verticalSpacing="sm" className={classes.documentTable}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>근거 자료</Table.Th>
                      <Table.Th>출처 API</Table.Th>
                      <Table.Th>원본 데이터</Table.Th>
                      <Table.Th>검색 준비 상태</Table.Th>
                      <Table.Th>내용 미리보기</Table.Th>
                      <Table.Th>상세</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(documents?.items ?? []).length > 0 ? (
                      documents!.items.map((document) => (
                        <Table.Tr key={document.id}>
                          <Table.Td>
                            <Text fw={700} size="sm" lineClamp={1}>{document.title}</Text>
                            <Text size="xs" c="dimmed" lineClamp={1}>{document.address ?? document.content_type ?? "메타데이터 없음"}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm">{document.source_label}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" lineClamp={2}>{document.source_item_title ?? document.source_item_id}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Badge variant="light" color={documentTone(document.embedding_status)}>
                              {document.status_label}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" lineClamp={3}>{document.content_excerpt}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Button size="compact-xs" variant="subtle" onClick={() => setSelectedDocument(document)}>
                              보기
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={6} text="조건에 맞는 AI 검색 근거 자료가 없습니다." />
                    )}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            </Paper>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="catalogs" pt="md">
          <Stack gap="md">
            <PanelHeader
              title="지역/분류 기준표"
              description="지역은 시/도에서 시/군/구로, 관광 분류는 대분류에서 중분류와 소분류로 좁혀서 확인합니다."
            />
            <Stack gap="md">
              <RegionCatalogExplorer
                rootRows={catalogs?.regions ?? []}
                rootTotal={catalogs?.region_total ?? 0}
                rootOffset={catalogs?.region_offset ?? regionOffset}
                childRows={regionChildrenCatalogs?.regions ?? []}
                childTotal={regionChildrenCatalogs?.region_total ?? 0}
                childOffset={regionChildrenCatalogs?.region_offset ?? regionChildOffset}
                searchRows={regionSearchCatalogs?.regions ?? []}
                searchTotal={regionSearchCatalogs?.region_total ?? 0}
                searchOffset={regionSearchCatalogs?.region_offset ?? regionSearchOffset}
                loading={catalogsLoading}
                query={regionQuery}
                searchInput={regionSearchInput}
                selectedRegionCode={selectedRegionCode}
                syncedAt={overview.catalogs.find((catalog) => catalog.key === "tourapi_ldong")?.last_synced_at ?? null}
                onSearchInputChange={setRegionSearchInput}
                onSearch={() => {
                  setRegionSearchOffset(0);
                  setRegionQuery(regionSearchInput.trim());
                  setSelectedRegionCode(null);
                  setRegionChildOffset(0);
                }}
                onSelectedRegionChange={(value) => {
                  setSelectedRegionCode(value);
                  setRegionQuery("");
                  setRegionSearchInput("");
                  setRegionChildOffset(0);
                  setRegionSearchOffset(0);
                }}
                onRootPageChange={setRegionOffset}
                onChildPageChange={setRegionChildOffset}
                onSearchPageChange={setRegionSearchOffset}
                onRefresh={() => void loadCatalogs()}
              />
              <ClassificationCatalogExplorer
                level1Rows={catalogs?.classifications ?? []}
                level1Total={catalogs?.classification_total ?? 0}
                level1Offset={catalogs?.classification_offset ?? classificationOffset}
                level2Rows={classificationLevel2Catalogs?.classifications ?? []}
                level2Total={classificationLevel2Catalogs?.classification_total ?? 0}
                level2Offset={classificationLevel2Catalogs?.classification_offset ?? classificationLevel2Offset}
                level3Rows={classificationLevel3Catalogs?.classifications ?? []}
                level3Total={classificationLevel3Catalogs?.classification_total ?? 0}
                level3Offset={classificationLevel3Catalogs?.classification_offset ?? classificationLevel3Offset}
                searchRows={classificationSearchCatalogs?.classifications ?? []}
                searchTotal={classificationSearchCatalogs?.classification_total ?? 0}
                searchOffset={classificationSearchCatalogs?.classification_offset ?? classificationSearchOffset}
                loading={catalogsLoading}
                query={classificationQuery}
                searchInput={classificationSearchInput}
                selectedLevel1={selectedClassLevel1}
                selectedLevel2={selectedClassLevel2}
                syncedAt={overview.catalogs.find((catalog) => catalog.key === "tourapi_lcls")?.last_synced_at ?? null}
                onSearchInputChange={setClassificationSearchInput}
                onSearch={() => {
                  setClassificationSearchOffset(0);
                  setClassificationQuery(classificationSearchInput.trim());
                  setSelectedClassLevel1(null);
                  setSelectedClassLevel2(null);
                  setClassificationLevel2Offset(0);
                  setClassificationLevel3Offset(0);
                }}
                onSelectedLevel1Change={(value) => {
                  setSelectedClassLevel1(value);
                  setSelectedClassLevel2(null);
                  setClassificationQuery("");
                  setClassificationSearchInput("");
                  setClassificationLevel2Offset(0);
                  setClassificationLevel3Offset(0);
                  setClassificationSearchOffset(0);
                }}
                onSelectedLevel2Change={(value) => {
                  setSelectedClassLevel2(value);
                  setClassificationQuery("");
                  setClassificationSearchInput("");
                  setClassificationLevel3Offset(0);
                  setClassificationSearchOffset(0);
                }}
                onReset={() => {
                  setSelectedClassLevel1(null);
                  setSelectedClassLevel2(null);
                  setClassificationQuery("");
                  setClassificationSearchInput("");
                  setClassificationLevel2Offset(0);
                  setClassificationLevel3Offset(0);
                  setClassificationSearchOffset(0);
                }}
                onLevel1PageChange={setClassificationOffset}
                onLevel2PageChange={setClassificationLevel2Offset}
                onLevel3PageChange={setClassificationLevel3Offset}
                onSearchPageChange={setClassificationSearchOffset}
                onRefresh={() => void loadCatalogs()}
              />
            </Stack>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="purpose" pt="md">
          <Stack gap="md">
            <PanelHeader
              title="목적별 보기"
              description="기본은 전체 데이터 카탈로그입니다. 목적을 누르면 관련 API를 빠르게 확인하되, 전체 데이터 접근은 유지합니다."
            />
            <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
              {purposeOptions.filter((profile) => profile.value !== "all").map((profile) => {
                const relatedSources = (overview.sources ?? []).filter((source) => source.purpose_tags.includes(profile.value));
                return (
                  <Paper key={profile.value} withBorder p="md">
                    <Group justify="space-between" align="flex-start" mb="xs">
                      <div>
                        <Text fw={700}>{profile.label}</Text>
                        <Text size="xs" c="dimmed">{relatedSources.length}개 API 관련</Text>
                      </div>
                      <Button
                        size="compact-xs"
                        variant="light"
                        onClick={() => {
                          setPurpose(profile.value);
                          setActiveTab("apis");
                        }}
                      >
                        API 보기
                      </Button>
                    </Group>
                    <Stack gap={6}>
                      {relatedSources.length > 0 ? (
                        relatedSources.slice(0, 5).map((source) => (
                          <Group key={source.source_family} justify="space-between" wrap="nowrap">
                            <Text size="sm" lineClamp={1}>{cleanDisplayName(source.display_name)}</Text>
                            <Badge size="xs" variant="light" color={readinessTone(source.readiness_status)}>
                              {source.status_label}
                            </Badge>
                          </Group>
                        ))
                      ) : (
                        <Text size="sm" c="dimmed">관련 API가 아직 분류되지 않았습니다.</Text>
                      )}
                    </Stack>
                  </Paper>
                );
              })}
            </SimpleGrid>
          </Stack>
        </Tabs.Panel>
      </Tabs>

      <Drawer
        opened={selectedSource !== null}
        onClose={() => setSelectedSourceId(null)}
        title={selectedSource ? cleanDisplayName(selectedSource.display_name) : "데이터 API 상세"}
        position="right"
        size="lg"
        padding="md"
      >
        {selectedSource ? <SourceDetail source={selectedSource} /> : null}
      </Drawer>

      <Drawer
        opened={selectedDocument !== null}
        onClose={() => setSelectedDocument(null)}
        title={selectedDocument?.title ?? "AI 검색 근거 자료"}
        position="right"
        size="lg"
        padding="md"
      >
        {selectedDocument ? <DocumentDetail document={selectedDocument} /> : null}
      </Drawer>

      <Drawer
        opened={selectedItem !== null}
        onClose={() => setSelectedItem(null)}
        title={selectedItem?.title ?? "수집 데이터 상세"}
        position="right"
        size="lg"
        padding="md"
      >
        {selectedItem ? <TourismItemDetail item={selectedItem} /> : null}
      </Drawer>
    </Stack>
  );
}

function SummaryCard({
  label,
  value,
  description,
  icon,
}: {
  label: string;
  value: string;
  description: string;
  icon: ReactNode;
}) {
  return (
    <Paper withBorder p="md" className={classes.summaryCard}>
      <Group justify="space-between" align="flex-start">
        <Text c="dimmed" size="sm">{label}</Text>
        <div className={classes.summaryIcon}>{icon}</div>
      </Group>
      <Title order={3} className={classes.summaryValue}>{value}</Title>
      <Text size="xs" c="dimmed" mt={6}>{description}</Text>
    </Paper>
  );
}

function PanelHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <Text fw={700}>{title}</Text>
      <Text size="sm" c="dimmed">{description}</Text>
    </div>
  );
}

function FilterBar({ children }: { children: ReactNode }) {
  return (
    <Group gap="sm" align="flex-end" className={classes.filterBar}>
      {children}
    </Group>
  );
}

function ResultHeader({ loading, total, limit }: { loading: boolean; total: number; limit: number }) {
  return (
    <Group justify="space-between" px="md" py="xs" className={classes.resultHeader}>
      <Text size="xs" c="dimmed">
        {total > limit && limit > 0 ? `${formatNumber(total)}개 중 ${formatNumber(limit)}개 표시` : `${formatNumber(total)}개 표시`}
      </Text>
      {loading ? (
        <Group gap={6}>
          <Loader size="xs" />
          <Text size="xs" c="dimmed">조회 중</Text>
        </Group>
      ) : null}
    </Group>
  );
}

function FieldPreview({ fields }: { fields: string[] }) {
  return (
    <Stack gap={4}>
      {fields.slice(0, 3).map((field) => (
        <Badge key={field} size="xs" variant="light" color="gray" className={classes.fieldBadge}>
          {field}
        </Badge>
      ))}
      {fields.length > 3 ? <Text size="xs" c="dimmed">외 {fields.length - 3}개</Text> : null}
    </Stack>
  );
}

function SourceDetail({ source }: { source: DataSourceOverviewItem }) {
  const implementedOperations = source.operations.filter((operation) => operation.implemented || operation.workflow_enabled);
  return (
    <Stack gap="md">
      <Alert color={readinessTone(source.readiness_status)} icon={<IconDatabase size={16} />}>
        <Group gap="xs" mb={4}>
          <Badge variant="filled" color={readinessTone(source.readiness_status)}>
            {source.status_label}
          </Badge>
          <Badge variant="light" color="gray">
            {categoryLabel(source.category)}
          </Badge>
        </Group>
        <Text size="sm">{source.status_detail}</Text>
      </Alert>

      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">이 API의 존재 목적</Text>
        <Text size="sm">{source.purpose}</Text>
        <Text size="sm" c="dimmed" mt="xs">{source.example_use}</Text>
      </Paper>

      <SimpleGrid cols={2}>
        <DrawerMetric label="실제 저장 데이터" value={source.stored_count} />
        <DrawerMetric label="AI 검색 근거" value={source.evidence_count} />
        <DrawerMetric label="사진 자료" value={source.inventory.visual_assets} />
        <DrawerMetric label="경로/수요 신호" value={source.inventory.route_assets + source.inventory.signal_records} />
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <Paper withBorder p="md">
          <Text fw={700} size="sm" mb="xs">입력값</Text>
          <ChipList items={source.input_fields} />
        </Paper>
        <Paper withBorder p="md">
          <Text fw={700} size="sm" mb="xs">출력값</Text>
          <ChipList items={source.output_fields} />
        </Paper>
      </SimpleGrid>

      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">데이터가 쌓이는 방식</Text>
        <Text size="sm">{source.origin_description}</Text>
      </Paper>

      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">채울 수 있는 정보</Text>
        <ChipList items={source.supported_gaps.map(gapLabel)} />
      </Paper>

      <Accordion variant="contained">
        <Accordion.Item value="api-calls">
          <Accordion.Control>구현된 API 호출 목록</Accordion.Control>
          <Accordion.Panel>
            <Stack gap="xs">
              {implementedOperations.length > 0 ? (
                implementedOperations.map((operation) => (
                  <Group key={`${operation.tool_name}-${operation.operation}`} justify="space-between" align="flex-start" wrap="nowrap">
                    <div>
                      <Text size="sm" fw={600}>{operation.operation}</Text>
                      <Text size="xs" c="dimmed">{operation.purpose}</Text>
                    </div>
                    <Group gap={6} wrap="nowrap">
                      {operation.workflow_enabled ? <Badge size="xs" color="green" variant="light">자동 사용</Badge> : null}
                      <Badge size="xs" color={operation.implemented ? "blue" : "gray"} variant="light">
                        {operation.implemented ? "구현됨" : "예정"}
                      </Badge>
                    </Group>
                  </Group>
                ))
              ) : (
                <Text size="sm" c="dimmed">현재 구현된 API 호출이 없습니다.</Text>
              )}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="notes">
          <Accordion.Control>운영 메모</Accordion.Control>
          <Accordion.Panel>
            {source.notes.length > 0 ? (
              <ul className={classes.compactList}>
                {source.notes.map((note) => (
                  <li key={note}>
                    <Text size="sm">{note}</Text>
                  </li>
                ))}
              </ul>
            ) : (
              <Text size="sm" c="dimmed">별도 운영 메모가 없습니다.</Text>
            )}
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}

function DocumentDetail({ document }: { document: DataSourceDocumentPreview }) {
  return (
    <Stack gap="md">
      <Alert color={documentTone(document.embedding_status)} icon={<IconFileSearch size={16} />}>
        <Badge variant="filled" color={documentTone(document.embedding_status)} mb="xs">
          {document.status_label}
        </Badge>
        <Text size="sm">{document.usage_summary}</Text>
      </Alert>
      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">어디서 축적됐나</Text>
        <Text size="sm">{document.origin_summary}</Text>
        <Text size="xs" c="dimmed" mt="xs">출처 API: {document.source_label}</Text>
      </Paper>
      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">AI가 실제로 참고하는 문장</Text>
        <Text size="sm" className={classes.preline}>{document.content}</Text>
      </Paper>
      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">원본 연결</Text>
        <Text size="sm">원본 데이터: {document.source_item_title ?? document.source_item_id}</Text>
        <Text size="sm" c="dimmed">마지막 갱신: {formatKstDateTime(document.updated_at)}</Text>
      </Paper>
    </Stack>
  );
}

function TourismItemDetail({ item }: { item: DataSourceTourismItemPreview }) {
  return (
    <Stack gap="md">
      <SimpleGrid cols={2}>
        <DrawerMetric label="contentId" valueText={item.content_id} />
        <DrawerMetric label="유형" valueText={item.content_type_label} />
      </SimpleGrid>
      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">수집 출처</Text>
        <Text size="sm">{item.origin_summary}</Text>
        <Text size="sm" c="dimmed" mt="xs">마지막 수집: {formatKstDateTime(item.last_synced_at)}</Text>
      </Paper>
      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">현재 보유 내용</Text>
        <Group gap="xs" mb="xs">
          <Badge color={item.has_image ? "green" : "yellow"} variant="light">
            {item.has_image ? "이미지 있음" : "이미지 없음"}
          </Badge>
          <Badge color={item.has_ai_evidence ? "green" : "gray"} variant="light">
            {item.has_ai_evidence ? "AI 근거 있음" : "AI 근거 없음"}
          </Badge>
        </Group>
        <Text size="sm">{item.detail_summary}</Text>
      </Paper>
      <Paper withBorder p="md">
        <Text fw={700} size="sm" mb="xs">기준표 연결</Text>
        <Text size="sm">지역: {item.ldong_label ?? "지역 기준표 미연결"}</Text>
        <Text size="sm">관광 분류: {item.classification_label ?? "관광 분류 미연결"}</Text>
      </Paper>
    </Stack>
  );
}

function RegionCatalogExplorer({
  rootRows,
  rootTotal,
  rootOffset,
  childRows,
  childTotal,
  childOffset,
  searchRows,
  searchTotal,
  searchOffset,
  loading,
  query,
  searchInput,
  selectedRegionCode,
  syncedAt,
  onSearchInputChange,
  onSearch,
  onSelectedRegionChange,
  onRootPageChange,
  onChildPageChange,
  onSearchPageChange,
  onRefresh,
}: {
  rootRows: DataSourceRegionCatalogItem[];
  rootTotal: number;
  rootOffset: number;
  childRows: DataSourceRegionCatalogItem[];
  childTotal: number;
  childOffset: number;
  searchRows: DataSourceRegionCatalogItem[];
  searchTotal: number;
  searchOffset: number;
  loading: boolean;
  query: string;
  searchInput: string;
  selectedRegionCode: string | null;
  syncedAt: string | null;
  onSearchInputChange: (value: string) => void;
  onSearch: () => void;
  onSelectedRegionChange: (value: string | null) => void;
  onRootPageChange: (offset: number) => void;
  onChildPageChange: (offset: number) => void;
  onSearchPageChange: (offset: number) => void;
  onRefresh: () => void;
}) {
  const isSearchMode = query.trim().length > 0;
  const selectedRegion = rootRows.find((row) => row.region_code === selectedRegionCode) ?? null;

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="xs">
        <div>
          <Text fw={700}>지역 보기</Text>
          <Text size="xs" c="dimmed">시/도를 고른 뒤 시/군/구로 좁혀 봅니다.</Text>
        </div>
        <Badge variant="light" color="gray">시/도 {formatNumber(rootTotal)}개</Badge>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">기준표 동기화: {formatKstDateTime(syncedAt)}</Text>
      <Stack gap="sm" mb="sm">
        <FilterBar>
          <TextInput
            leftSection={<IconSearch size={15} />}
            placeholder="지역명 입력 후 Enter"
            value={searchInput}
            onChange={(event) => onSearchInputChange(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onSearch();
            }}
          />
          <Button variant="light" loading={loading} onClick={onSearch}>
            검색
          </Button>
          <Button variant="subtle" loading={loading} onClick={onRefresh}>
            다시 불러오기
          </Button>
        </FilterBar>
      </Stack>
      {isSearchMode ? (
        <CatalogSearchResults
          title={`"${query}" 지역 검색 결과`}
          rows={searchRows}
          total={searchTotal}
          offset={searchOffset}
          loading={loading}
          emptyText="조건에 맞는 지역이 없습니다."
          onPageChange={onSearchPageChange}
          renderRow={(row: DataSourceRegionCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={row.signgu_name ?? row.region_name}
              subtitle={row.signgu_name ? row.region_name : null}
              count={row.tourism_item_count}
              onClick={row.signgu_code ? undefined : () => onSelectedRegionChange(row.region_code)}
            />
          )}
        />
      ) : null}
      <SimpleGrid cols={{ base: 1, md: 2 }} className={classes.catalogColumns}>
        <CatalogColumn
          title="시/도"
          description="항목을 클릭하면 오른쪽에 시/군/구가 표시됩니다."
          rows={rootRows}
          total={rootTotal}
          offset={rootOffset}
          loading={loading}
          emptyText="표시할 시/도가 없습니다."
          onPageChange={onRootPageChange}
          renderRow={(row: DataSourceRegionCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={row.region_name}
              count={row.tourism_item_count}
              selected={row.region_code === selectedRegionCode}
              onClick={() => onSelectedRegionChange(row.region_code)}
            />
          )}
        />
        <CatalogColumn
          title={selectedRegion ? `${selectedRegion.region_name} 시/군/구` : "시/군/구"}
          description={selectedRegion ? "선택한 시/도에 속한 시/군/구입니다." : "왼쪽에서 시/도를 먼저 선택하세요."}
          rows={selectedRegionCode ? childRows : []}
          total={selectedRegionCode ? childTotal : 0}
          offset={childOffset}
          loading={loading}
          emptyText={selectedRegionCode ? "표시할 시/군/구가 없습니다." : "선택된 시/도가 없습니다."}
          onPageChange={onChildPageChange}
          renderRow={(row: DataSourceRegionCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={row.signgu_name ?? row.region_name}
              count={row.tourism_item_count}
            />
          )}
        />
      </SimpleGrid>
    </Paper>
  );
}

function ClassificationCatalogExplorer({
  level1Rows,
  level1Total,
  level1Offset,
  level2Rows,
  level2Total,
  level2Offset,
  level3Rows,
  level3Total,
  level3Offset,
  searchRows,
  searchTotal,
  searchOffset,
  loading,
  query,
  searchInput,
  selectedLevel1,
  selectedLevel2,
  syncedAt,
  onSearchInputChange,
  onSearch,
  onSelectedLevel1Change,
  onSelectedLevel2Change,
  onReset,
  onLevel1PageChange,
  onLevel2PageChange,
  onLevel3PageChange,
  onSearchPageChange,
  onRefresh,
}: {
  level1Rows: DataSourceClassificationCatalogItem[];
  level1Total: number;
  level1Offset: number;
  level2Rows: DataSourceClassificationCatalogItem[];
  level2Total: number;
  level2Offset: number;
  level3Rows: DataSourceClassificationCatalogItem[];
  level3Total: number;
  level3Offset: number;
  searchRows: DataSourceClassificationCatalogItem[];
  searchTotal: number;
  searchOffset: number;
  loading: boolean;
  query: string;
  searchInput: string;
  selectedLevel1: string | null;
  selectedLevel2: string | null;
  syncedAt: string | null;
  onSearchInputChange: (value: string) => void;
  onSearch: () => void;
  onSelectedLevel1Change: (value: string | null) => void;
  onSelectedLevel2Change: (value: string | null) => void;
  onReset: () => void;
  onLevel1PageChange: (offset: number) => void;
  onLevel2PageChange: (offset: number) => void;
  onLevel3PageChange: (offset: number) => void;
  onSearchPageChange: (offset: number) => void;
  onRefresh: () => void;
}) {
  const isSearchMode = query.trim().length > 0;
  const selectedLevel1Row = level1Rows.find((row) => row.code_path[0] === selectedLevel1) ?? null;
  const selectedLevel2Row = level2Rows.find((row) => row.code_path[1] === selectedLevel2) ?? null;

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="xs">
        <div>
          <Text fw={700}>관광 분류 보기</Text>
          <Text size="xs" c="dimmed">대분류, 중분류, 소분류 순서로 좁혀 봅니다.</Text>
        </div>
        <Badge variant="light" color="gray">대분류 {formatNumber(level1Total)}개</Badge>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">기준표 동기화: {formatKstDateTime(syncedAt)}</Text>
      <Stack gap="sm" mb="sm">
        <FilterBar>
          <TextInput
            leftSection={<IconSearch size={15} />}
            placeholder="분류명 입력 후 Enter"
            value={searchInput}
            onChange={(event) => onSearchInputChange(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onSearch();
            }}
          />
          <Button variant="light" loading={loading} onClick={onSearch}>
            검색
          </Button>
          <Button variant="subtle" loading={loading} onClick={onRefresh}>
            다시 불러오기
          </Button>
        </FilterBar>
        {selectedLevel1 || selectedLevel2 ? (
          <Button variant="subtle" size="xs" onClick={onReset}>
            전체 대분류로 돌아가기
          </Button>
        ) : null}
      </Stack>
      {isSearchMode ? (
        <CatalogSearchResults
          title={`"${query}" 관광 분류 검색 결과`}
          rows={searchRows}
          total={searchTotal}
          offset={searchOffset}
          loading={loading}
          emptyText="조건에 맞는 관광 분류가 없습니다."
          onPageChange={onSearchPageChange}
          renderRow={(row: DataSourceClassificationCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={classificationName(row)}
              count={row.tourism_item_count}
              onClick={row.code_path.length < 3 ? () => {
                onSelectedLevel1Change(row.code_path[0] ?? null);
                if (row.code_path.length > 1) onSelectedLevel2Change(row.code_path[1] ?? null);
              } : undefined}
            />
          )}
        />
      ) : null}
      <SimpleGrid cols={{ base: 1, md: 3 }} className={classes.catalogColumns}>
        <CatalogColumn
          title="대분류"
          description="항목을 클릭하면 중분류가 오른쪽에 표시됩니다."
          rows={level1Rows}
          total={level1Total}
          offset={level1Offset}
          loading={loading}
          emptyText="표시할 대분류가 없습니다."
          onPageChange={onLevel1PageChange}
          renderRow={(row: DataSourceClassificationCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={classificationName(row)}
              count={row.tourism_item_count}
              selected={row.code_path[0] === selectedLevel1}
              onClick={() => onSelectedLevel1Change(row.code_path[0] ?? null)}
            />
          )}
        />
        <CatalogColumn
          title={selectedLevel1Row ? `${classificationName(selectedLevel1Row)} 중분류` : "중분류"}
          description={selectedLevel1 ? "선택한 대분류의 중분류입니다." : "왼쪽에서 대분류를 먼저 선택하세요."}
          rows={selectedLevel1 ? level2Rows : []}
          total={selectedLevel1 ? level2Total : 0}
          offset={level2Offset}
          loading={loading}
          emptyText={selectedLevel1 ? "표시할 중분류가 없습니다." : "선택된 대분류가 없습니다."}
          onPageChange={onLevel2PageChange}
          renderRow={(row: DataSourceClassificationCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={classificationName(row)}
              count={row.tourism_item_count}
              selected={row.code_path[1] === selectedLevel2}
              onClick={() => onSelectedLevel2Change(row.code_path[1] ?? null)}
            />
          )}
        />
        <CatalogColumn
          title={selectedLevel2Row ? `${classificationName(selectedLevel2Row)} 소분류` : "소분류"}
          description={selectedLevel2 ? "선택한 중분류의 소분류입니다." : "가운데에서 중분류를 먼저 선택하세요."}
          rows={selectedLevel2 ? level3Rows : []}
          total={selectedLevel2 ? level3Total : 0}
          offset={level3Offset}
          loading={loading}
          emptyText={selectedLevel2 ? "표시할 소분류가 없습니다." : "선택된 중분류가 없습니다."}
          onPageChange={onLevel3PageChange}
          renderRow={(row: DataSourceClassificationCatalogItem) => (
            <CatalogListRow
              key={row.id}
              title={classificationName(row)}
              count={row.tourism_item_count}
            />
          )}
        />
      </SimpleGrid>
    </Paper>
  );
}

function CatalogSearchResults<T>({
  title,
  rows,
  total,
  offset,
  loading,
  emptyText,
  onPageChange,
  renderRow,
}: {
  title: string;
  rows: T[];
  total: number;
  offset: number;
  loading: boolean;
  emptyText: string;
  onPageChange: (offset: number) => void;
  renderRow: (row: T) => ReactNode;
}) {
  return (
    <div className={classes.catalogSearchResults}>
      <Group justify="space-between" mb="xs">
        <Text fw={700} size="sm">{title}</Text>
        <Badge variant="light" color="gray">{formatNumber(total)}개</Badge>
      </Group>
      <Stack gap={6}>
        {rows.length > 0 ? rows.map(renderRow) : <Text size="sm" c="dimmed">{emptyText}</Text>}
      </Stack>
      <PaginationFooter offset={offset} limit={30} total={total} loading={loading} onPageChange={onPageChange} />
    </div>
  );
}

function CatalogColumn<T>({
  title,
  description,
  rows,
  total,
  offset,
  loading,
  emptyText,
  onPageChange,
  renderRow,
}: {
  title: string;
  description: string;
  rows: T[];
  total: number;
  offset: number;
  loading: boolean;
  emptyText: string;
  onPageChange: (offset: number) => void;
  renderRow: (row: T) => ReactNode;
}) {
  return (
    <div className={classes.catalogColumn}>
      <Group justify="space-between" align="flex-start" mb="xs">
        <div>
          <Text size="sm" fw={700}>{title}</Text>
          <Text size="xs" c="dimmed">{description}</Text>
        </div>
        <Badge variant="light" color="gray">{formatNumber(total)}개</Badge>
      </Group>
      <ScrollArea h={360}>
        <Stack gap={6}>
          {rows.length > 0 ? rows.map(renderRow) : <Text size="sm" c="dimmed">{emptyText}</Text>}
        </Stack>
      </ScrollArea>
      <PaginationFooter offset={offset} limit={30} total={total} loading={loading} onPageChange={onPageChange} />
    </div>
  );
}

function CatalogListRow({
  title,
  subtitle,
  count,
  selected = false,
  onClick,
}: {
  title: string;
  subtitle?: string | null;
  count: number;
  selected?: boolean;
  onClick?: () => void;
}) {
  const className = [
    classes.catalogListRow,
    onClick ? classes.clickableCatalogRow : "",
    selected ? classes.selectedCatalogRow : "",
  ].filter(Boolean).join(" ");
  const content = (
    <Group justify="space-between" align="flex-start" wrap="nowrap">
      <div>
        <Text size="sm" fw={700}>{title}</Text>
        {subtitle ? <Text size="xs" c="dimmed">{subtitle}</Text> : null}
      </div>
      <Badge variant="light" color={count > 0 ? "green" : "gray"}>
        관광 데이터 {formatNumber(count)}
      </Badge>
    </Group>
  );

  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        {content}
      </button>
    );
  }

  return <div className={className}>{content}</div>;
}

function PaginationFooter({
  offset,
  limit,
  total,
  loading,
  onPageChange,
}: {
  offset: number;
  limit: number;
  total: number;
  loading: boolean;
  onPageChange: (offset: number) => void;
}) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const currentPage = total === 0 ? 0 : Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <Group justify="space-between" mt="sm" className={classes.paginationFooter}>
      <Text size="xs" c="dimmed">
        {formatNumber(start)}-{formatNumber(end)} / {formatNumber(total)}
        {totalPages > 0 ? ` · ${formatNumber(currentPage)}/${formatNumber(totalPages)}쪽` : ""}
      </Text>
      <Group gap="xs">
        <Button
          size="compact-xs"
          variant="subtle"
          disabled={loading || offset <= 0}
          onClick={() => onPageChange(Math.max(0, offset - limit))}
        >
          이전
        </Button>
        <Button
          size="compact-xs"
          variant="light"
          disabled={loading || offset + limit >= total}
          onClick={() => onPageChange(offset + limit)}
        >
          다음
        </Button>
      </Group>
    </Group>
  );
}

function DrawerMetric({ label, value, valueText }: { label: string; value?: number; valueText?: string }) {
  return (
    <Paper withBorder p="md" className={classes.drawerMetric}>
      <Text c="dimmed" size="xs">{label}</Text>
      <Title order={4}>{valueText ?? formatNumber(value ?? 0)}</Title>
    </Paper>
  );
}

function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <Text size="sm" c="dimmed">아직 분류된 항목이 없습니다.</Text>;
  }
  return (
    <Group gap="xs">
      {items.map((item) => (
        <Badge key={item} variant="light" color="gray" className={classes.fieldBadge}>
          {item}
        </Badge>
      ))}
    </Group>
  );
}

function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <Table.Tr>
      <Table.Td colSpan={colSpan}>
        <Text c="dimmed" ta="center" py="lg">{text}</Text>
      </Table.Td>
    </Table.Tr>
  );
}

function statusOptions() {
  return [
    { value: "all", label: "전체 상태" },
    { value: "ready", label: "연결됨" },
    { value: "available", label: "수동 확인 가능" },
    { value: "setup_required", label: "키 연결 필요" },
    { value: "off", label: "꺼짐" },
    { value: "planned", label: "준비 중" },
  ];
}

function documentStatusOptions() {
  return [
    { value: "all", label: "전체 검색 상태" },
    { value: "indexed", label: "AI 검색 가능" },
    { value: "pending", label: "색인 대기" },
    { value: "failed", label: "색인 실패" },
  ];
}

function classificationName(row: DataSourceClassificationCatalogItem) {
  return row.name_path[row.name_path.length - 1] ?? row.full_name;
}

function cleanDisplayName(value: string) {
  return value.replace(/_GW$/u, "");
}

function categoryLabel(value: string) {
  return CATEGORY_LABELS[value] ?? "기타 데이터";
}

function gapLabel(value: string) {
  return GAP_LABELS[value] ?? "추가 확인 정보";
}

function purposeLabel(value: string | null) {
  return PURPOSE_LABELS[value ?? "all"] ?? "선택 목적";
}

function contentTypeLabel(value: string) {
  const labels: Record<string, string> = {
    attraction: "관광지",
    event: "행사/축제",
    accommodation: "숙박",
    leisure: "레포츠",
    culture: "문화시설",
    shopping: "쇼핑",
    restaurant: "음식점",
  };
  return labels[value] ?? value;
}

function relevanceScore(source: DataSourceOverviewItem, selectedPurpose: string | null) {
  if (!selectedPurpose || selectedPurpose === "all") return 0;
  return source.purpose_tags.includes(selectedPurpose) ? 1 : 0;
}

function readinessTone(status: string): StatusTone {
  if (status === "ready") return "green";
  if (status === "available") return "blue";
  if (status === "setup_required") return "yellow";
  if (status === "off") return "gray";
  return "gray";
}

function documentTone(status: string): StatusTone {
  if (status === "indexed") return "green";
  if (status === "failed") return "red";
  if (status === "pending") return "yellow";
  return "gray";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR").format(value);
}
