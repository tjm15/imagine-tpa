import { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { ArrowLeft, RefreshCcw, AlertTriangle, CheckCircle2, Search, FileText, Upload } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Input } from './ui/input';
import { DebugGraph3D, DebugGraphData, DebugGraphNode } from './DebugGraph3D';
import { IngestRunInspector } from './views/inspector/IngestRunInspector';
import { PolicyInspector } from './views/inspector/PolicyInspector';

type ApiResult<T> = {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
  rawText?: string;
};

type HealthPayload = { status?: string; db?: string; detail?: unknown };
type IngestJob = {
  ingest_job_id: string;
  ingest_batch_id?: string | null;
  authority_id?: string | null;
  plan_cycle_id?: string | null;
  job_type?: string | null;
  status?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_text?: string | null;
};
type IngestBatch = {
  ingest_batch_id: string;
  source_system?: string | null;
  authority_id?: string | null;
  plan_cycle_id?: string | null;
  status?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

type DebugOverview = {
  counts: Record<string, number>;
  generated_at?: string | null;
};

type IngestRun = {
  id: string;
  ingest_batch_id?: string | null;
  authority_id?: string | null;
  plan_cycle_id?: string | null;
  pipeline_version?: string | null;
  status?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
};

type IngestRunStep = {
  id: string;
  step_name?: string | null;
  status?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  error_text?: string | null;
  inputs_jsonb?: Record<string, any> | null;
  outputs_jsonb?: Record<string, any> | null;
};

type DebugDocument = {
  id: string;
  authority_id: string;
  plan_cycle_id?: string | null;
  run_id?: string | null;
  title?: string | null;
  raw_blob_path?: string | null;
  raw_sha256?: string | null;
  raw_bytes?: number | null;
  raw_source_uri?: string | null;
  created_at?: string | null;
};

type DocumentCoverage = {
  document_id: string;
  run_id?: string | null;
  counts?: Record<string, number>;
  assertions?: Array<{ check: string; ok: boolean; detail: string }>;
  parse_bundle?: Record<string, any>;
  raw?: Record<string, any>;
};

type ToolRun = {
  id: string;
  ingest_batch_id?: string | null;
  run_id?: string | null;
  tool_name?: string | null;
  status?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  confidence_hint?: string | null;
  uncertainty_note?: string | null;
  inputs_logged?: Record<string, any> | null;
  outputs_logged?: Record<string, any> | null;
};

type PromptRow = {
  prompt_id: string;
  name?: string | null;
  purpose?: string | null;
  created_at?: string | null;
  created_by?: string | null;
};

type PromptVersion = {
  prompt_id: string;
  prompt_version: number;
  input_schema_ref?: string | null;
  output_schema_ref?: string | null;
  created_at?: string | null;
  created_by?: string | null;
};

type RunSummary = {
  id: string;
  profile?: string | null;
  culp_stage_id?: string | null;
  created_at?: string | null;
};

type VisualAssetSummary = {
  id: string;
  document_id?: string | null;
  page_number?: number | null;
  asset_type?: string | null;
  blob_path?: string | null;
  created_at?: string | null;
  semantic_asset_type?: string | null;
  semantic_asset_subtype?: string | null;
  assertion_count?: number | null;
  mask_count?: number | null;
  region_count?: number | null;
  semantic_count?: number | null;
  georef_status?: string | null;
  georef_tool_run_id?: string | null;
  transform_id?: string | null;
  metadata_jsonb?: Record<string, any> | null;
};

type VisualAssetDetail = {
  visual_asset?: Record<string, any> | null;
  semantic_outputs?: Array<Record<string, any>>;
  regions?: Array<Record<string, any>>;
  masks?: Array<Record<string, any>>;
  transform?: Record<string, any> | null;
  projection_artifacts?: Array<Record<string, any>>;
};

const API_PREFIX = '/api';

type EndpointError = {
  label: string;
  status: number;
  error: string;
  rawText?: string;
};

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<ApiResult<T>> {
  try {
    const resp = await fetch(`${API_PREFIX}${path}`, {
      signal,
      headers: { accept: 'application/json' },
    });
    const text = await resp.text();
    let data: T | null = null;
    if (text) {
      try {
        data = JSON.parse(text) as T;
      } catch {
        data = null;
      }
    }
    if (!resp.ok) {
      return {
        ok: false,
        status: resp.status,
        data,
        error: (data as any)?.detail ? JSON.stringify((data as any).detail) : text || resp.statusText,
        rawText: text || undefined,
      };
    }
    return { ok: true, status: resp.status, data, rawText: text || undefined };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: String((err as Error).message || err),
      rawText: undefined,
    };
  }
}

async function postJson<T>(path: string, body: Record<string, any>): Promise<ApiResult<T>> {
  try {
    const resp = await fetch(`${API_PREFIX}${path}`, {
      method: 'POST',
      headers: { accept: 'application/json', 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const text = await resp.text();
    let data: T | null = null;
    if (text) {
      try {
        data = JSON.parse(text) as T;
      } catch {
        data = null;
      }
    }
    if (!resp.ok) {
      return {
        ok: false,
        status: resp.status,
        data,
        error: (data as any)?.detail ? JSON.stringify((data as any).detail) : text || resp.statusText,
        rawText: text || undefined,
      };
    }
    return { ok: true, status: resp.status, data, rawText: text || undefined };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: String((err as Error).message || err),
      rawText: undefined,
    };
  }
}

function formatDate(value?: string | null): string {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function statusTone(status?: string | null): 'ok' | 'warn' | 'neutral' {
  const value = (status || '').toLowerCase();
  if (value.includes('ok') || value.includes('ready') || value.includes('success')) return 'ok';
  if (value.includes('error') || value.includes('fail') || value.includes('down')) return 'warn';
  return 'neutral';
}

function StatusBadge({ label }: { label: string }) {
  const tone = statusTone(label);
  const styles: Record<string, { color: string; border: string; bg: string }> = {
    ok: {
      color: 'var(--color-success)',
      border: 'rgba(16, 185, 129, 0.35)',
      bg: 'rgba(16, 185, 129, 0.08)',
    },
    warn: {
      color: 'var(--color-warning)',
      border: 'rgba(234, 88, 12, 0.35)',
      bg: 'rgba(234, 88, 12, 0.08)',
    },
    neutral: {
      color: 'var(--color-text)',
      border: 'var(--color-neutral-300)',
      bg: 'rgba(255, 255, 255, 0.7)',
    },
  };
  const palette = styles[tone];
  return (
    <Badge
      variant="outline"
      className="font-medium"
      style={{ color: palette.color, borderColor: palette.border, backgroundColor: palette.bg }}
    >
      {label}
    </Badge>
  );
}

export function DebugView() {
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [endpointErrors, setEndpointErrors] = useState<EndpointError[]>([]);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [ready, setReady] = useState<HealthPayload | null>(null);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [batches, setBatches] = useState<IngestBatch[]>([]);
  const [schemas, setSchemas] = useState<string[]>([]);
  const [overview, setOverview] = useState<DebugOverview | null>(null);
  const [ingestRuns, setIngestRuns] = useState<IngestRun[]>([]);
  const [selectedIngestRunId, setSelectedIngestRunId] = useState<string | null>(null);
  const [ingestRunSteps, setIngestRunSteps] = useState<IngestRunStep[]>([]);
  const [documents, setDocuments] = useState<DebugDocument[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [documentCoverage, setDocumentCoverage] = useState<DocumentCoverage | null>(null);
  const [documentCoverageError, setDocumentCoverageError] = useState<EndpointError | null>(null);
  const [toolRuns, setToolRuns] = useState<ToolRun[]>([]);
  const [georefRuns, setGeorefRuns] = useState<ToolRun[]>([]);
  const [selectedToolRunId, setSelectedToolRunId] = useState<string | null>(null);
  const [prompts, setPrompts] = useState<PromptRow[]>([]);
  const [promptVersions, setPromptVersions] = useState<PromptVersion[]>([]);
  const [traceRuns, setTraceRuns] = useState<RunSummary[]>([]);
  const [traceMode, setTraceMode] = useState<'summary' | 'inspect' | 'forensic'>('summary');
  const [traceGraph, setTraceGraph] = useState<DebugGraphData | null>(null);
  const [traceError, setTraceError] = useState<EndpointError | null>(null);
  const [selectedTraceRunId, setSelectedTraceRunId] = useState<string | null>(null);
  const [kgGraph, setKgGraph] = useState<DebugGraphData | null>(null);
  const [kgError, setKgError] = useState<EndpointError | null>(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState<DebugGraphNode | null>(null);
  const [kgLoading, setKgLoading] = useState(false);
  const [kgNodeTypeFilter, setKgNodeTypeFilter] = useState('');
  const [kgLimit, setKgLimit] = useState('500');
  const [visualAssets, setVisualAssets] = useState<VisualAssetSummary[]>([]);
  const [selectedVisualAssetId, setSelectedVisualAssetId] = useState<string | null>(null);
  const [visualAssetDetail, setVisualAssetDetail] = useState<VisualAssetDetail | null>(null);
  const [visualAssetError, setVisualAssetError] = useState<EndpointError | null>(null);
  const [selectedRunStepId, setSelectedRunStepId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // New state for sub-views
  const [view, setView] = useState<'dashboard' | 'run-inspector' | 'policy-inspector'>('dashboard');
  const [inspectRunId, setInspectRunId] = useState<string | null>(null);
  const [inspectDocId, setInspectDocId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUpload] = useState(false);

  const envLabel = useMemo(() => (import.meta.env.DEV ? 'dev' : 'prod'), []);

  const latestPromptVersion = useMemo(() => {
    const map = new Map<string, number>();
    promptVersions.forEach((version) => {
      const current = map.get(version.prompt_id);
      if (current === undefined || version.prompt_version > current) {
        map.set(version.prompt_id, version.prompt_version);
      }
    });
    return map;
  }, [promptVersions]);

  const toolRunById = useMemo(() => {
    const map = new Map<string, ToolRun>();
    [...toolRuns, ...georefRuns].forEach((run) => {
      map.set(run.id, run);
    });
    return map;
  }, [toolRuns, georefRuns]);

  const selectedToolRun = selectedToolRunId ? toolRunById.get(selectedToolRunId) || null : null;
  const selectedRunStep = selectedRunStepId
    ? ingestRunSteps.find((step) => step.id === selectedRunStepId) || null
    : null;

  useEffect(() => {
    if (selectedToolRunId && !toolRunById.has(selectedToolRunId)) {
      setSelectedToolRunId(null);
    }
  }, [selectedToolRunId, toolRunById]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUpload(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/debug/ingest/upload', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        // Reload to show the new run
        setTimeout(() => load(), 1000);
      } else {
        console.error('Upload failed');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setUpload(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setEndpointErrors([]);
    const [
      healthRes,
      readyRes,
      jobsRes,
      batchesRes,
      schemasRes,
      overviewRes,
      ingestRunsRes,
      documentsRes,
      toolRunsRes,
      georefRunsRes,
      promptsRes,
      traceRunsRes,
      visualAssetsRes,
    ] = await Promise.all([
      fetchJson<HealthPayload>('/healthz', signal),
      fetchJson<HealthPayload>('/readyz', signal),
      fetchJson<{ ingest_jobs: IngestJob[] }>('/ingest/jobs?limit=10', signal),
      fetchJson<{ ingest_batches: IngestBatch[] }>('/ingest/batches?limit=10', signal),
      fetchJson<{ schemas: string[] }>('/spec/schemas', signal),
      fetchJson<DebugOverview>('/debug/overview', signal),
      fetchJson<{ ingest_runs: IngestRun[] }>('/debug/ingest/runs?limit=20', signal),
      fetchJson<{ documents: DebugDocument[] }>('/debug/documents?limit=25', signal),
      fetchJson<{ tool_runs: ToolRun[] }>('/debug/tool-runs?limit=30', signal),
      fetchJson<{ tool_runs: ToolRun[] }>('/debug/tool-runs?tool_name=auto_georef&limit=50', signal),
      fetchJson<{ prompts: PromptRow[]; prompt_versions: PromptVersion[] }>('/debug/prompts', signal),
      fetchJson<{ runs: RunSummary[] }>('/debug/runs?limit=20', signal),
      fetchJson<{ visual_assets: VisualAssetSummary[] }>('/debug/visual-assets?limit=40', signal),
    ]);

    const nextErrors: EndpointError[] = [];
    if (!healthRes.ok)
      nextErrors.push({ label: 'healthz', status: healthRes.status, error: healthRes.error || 'unavailable', rawText: healthRes.rawText });
    if (!readyRes.ok)
      nextErrors.push({ label: 'readyz', status: readyRes.status, error: readyRes.error || 'unavailable', rawText: readyRes.rawText });
    if (!jobsRes.ok)
      nextErrors.push({ label: 'ingest jobs', status: jobsRes.status, error: jobsRes.error || 'unavailable', rawText: jobsRes.rawText });
    if (!batchesRes.ok)
      nextErrors.push({
        label: 'ingest batches',
        status: batchesRes.status,
        error: batchesRes.error || 'unavailable',
        rawText: batchesRes.rawText,
      });
    if (!schemasRes.ok)
      nextErrors.push({ label: 'schemas', status: schemasRes.status, error: schemasRes.error || 'unavailable', rawText: schemasRes.rawText });
    if (!overviewRes.ok)
      nextErrors.push({
        label: 'debug overview',
        status: overviewRes.status,
        error: overviewRes.error || 'unavailable',
        rawText: overviewRes.rawText,
      });
    if (!ingestRunsRes.ok)
      nextErrors.push({
        label: 'ingest runs',
        status: ingestRunsRes.status,
        error: ingestRunsRes.error || 'unavailable',
        rawText: ingestRunsRes.rawText,
      });
    if (!documentsRes.ok)
      nextErrors.push({
        label: 'documents',
        status: documentsRes.status,
        error: documentsRes.error || 'unavailable',
        rawText: documentsRes.rawText,
      });
    if (!toolRunsRes.ok)
      nextErrors.push({
        label: 'tool runs',
        status: toolRunsRes.status,
        error: toolRunsRes.error || 'unavailable',
        rawText: toolRunsRes.rawText,
      });
    if (!georefRunsRes.ok)
      nextErrors.push({
        label: 'georef attempts',
        status: georefRunsRes.status,
        error: georefRunsRes.error || 'unavailable',
        rawText: georefRunsRes.rawText,
      });
    if (!promptsRes.ok)
      nextErrors.push({ label: 'prompts', status: promptsRes.status, error: promptsRes.error || 'unavailable', rawText: promptsRes.rawText });
    if (!traceRunsRes.ok)
      nextErrors.push({ label: 'runs', status: traceRunsRes.status, error: traceRunsRes.error || 'unavailable', rawText: traceRunsRes.rawText });
    if (!visualAssetsRes.ok)
      nextErrors.push({
        label: 'visual assets',
        status: visualAssetsRes.status,
        error: visualAssetsRes.error || 'unavailable',
        rawText: visualAssetsRes.rawText,
      });

    setHealth(healthRes.data);
    setReady(readyRes.data);
    setJobs(jobsRes.data?.ingest_jobs || []);
    setBatches(batchesRes.data?.ingest_batches || []);
    setSchemas(schemasRes.data?.schemas || []);
    setOverview(overviewRes.data || null);
    setIngestRuns(ingestRunsRes.data?.ingest_runs || []);
    setDocuments(documentsRes.data?.documents || []);
    setToolRuns(toolRunsRes.data?.tool_runs || []);
    setGeorefRuns(georefRunsRes.data?.tool_runs || []);
    setPrompts(promptsRes.data?.prompts || []);
    setPromptVersions(promptsRes.data?.prompt_versions || []);
    setTraceRuns(traceRunsRes.data?.runs || []);
    setVisualAssets(visualAssetsRes.data?.visual_assets || []);
    setEndpointErrors(nextErrors);
    setLastUpdated(new Date().toLocaleString());
    setLoading(false);
  }, []);

  const handleResetIngest = useCallback(async (payload: Record<string, any>) => {
    const res = await postJson<{ jobs_updated: number; runs_updated: number; batches_updated: number }>(
      '/debug/ingest/reset',
      payload,
    );
    if (res.ok) {
      const counts = res.data || { jobs_updated: 0, runs_updated: 0, batches_updated: 0 };
      setActionMessage(`Reset complete: ${counts.jobs_updated} jobs, ${counts.runs_updated} runs, ${counts.batches_updated} batches.`);
      load();
    } else {
      setActionMessage(`Reset failed: ${res.error || 'unknown error'}`);
    }
  }, [load]);

  const handleRequeueJob = useCallback(async (ingestJobId: string) => {
    const res = await postJson<{ ingest_job_id: string; enqueued: boolean }>('/debug/ingest/requeue', {
      ingest_job_id: ingestJobId,
    });
    if (res.ok) {
      setActionMessage(`Requeued job ${ingestJobId.slice(0, 8)}.`);
      load();
    } else {
      setActionMessage(`Requeue failed: ${res.error || 'unknown error'}`);
    }
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (!selectedIngestRunId && ingestRuns.length > 0) {
      setSelectedIngestRunId(ingestRuns[0].id);
    }
  }, [ingestRuns, selectedIngestRunId]);

  useEffect(() => {
    if (!selectedRunStepId && ingestRunSteps.length > 0) {
      setSelectedRunStepId(ingestRunSteps[0].id);
    }
  }, [ingestRunSteps, selectedRunStepId]);

  useEffect(() => {
    if (!selectedVisualAssetId && visualAssets.length > 0) {
      setSelectedVisualAssetId(visualAssets[0].id);
    }
  }, [visualAssets, selectedVisualAssetId]);

  useEffect(() => {
    if (!selectedTraceRunId && traceRuns.length > 0) {
      setSelectedTraceRunId(traceRuns[0].id);
    }
  }, [traceRuns, selectedTraceRunId]);

  useEffect(() => {
    if (!selectedIngestRunId) {
      setIngestRunSteps([]);
      setSelectedRunStepId(null);
      return;
    }
    setSelectedRunStepId(null);
    const controller = new AbortController();
    fetchJson<{ steps: IngestRunStep[] }>(`/debug/ingest/run-steps?run_id=${selectedIngestRunId}`, controller.signal)
      .then((res) => {
        if (res.ok) {
          setIngestRunSteps(res.data?.steps || []);
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [selectedIngestRunId]);

  useEffect(() => {
    if (!selectedDocumentId) {
      setDocumentCoverage(null);
      setDocumentCoverageError(null);
      return;
    }
    const controller = new AbortController();
    fetchJson<DocumentCoverage>(`/ingest/documents/${selectedDocumentId}/coverage`, controller.signal)
      .then((res) => {
        if (res.ok) {
          setDocumentCoverage(res.data);
          setDocumentCoverageError(null);
        } else {
          setDocumentCoverageError({
            label: 'document coverage',
            status: res.status,
            error: res.error || 'unavailable',
            rawText: res.rawText,
          });
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [selectedDocumentId]);

  useEffect(() => {
    if (!selectedDocumentId) {
      return;
    }
    const controller = new AbortController();
    fetchJson<{ visual_assets: VisualAssetSummary[] }>(
      `/debug/visual-assets?document_id=${selectedDocumentId}&limit=40`,
      controller.signal,
    )
      .then((res) => {
        if (res.ok) {
          setVisualAssets(res.data?.visual_assets || []);
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [selectedDocumentId]);

  useEffect(() => {
    if (!selectedVisualAssetId) {
      setVisualAssetDetail(null);
      setVisualAssetError(null);
      return;
    }
    const controller = new AbortController();
    fetchJson<VisualAssetDetail>(`/debug/visual-assets/${selectedVisualAssetId}`, controller.signal)
      .then((res) => {
        if (res.ok) {
          setVisualAssetDetail(res.data || null);
          setVisualAssetError(null);
        } else {
          setVisualAssetError({
            label: 'visual asset detail',
            status: res.status,
            error: res.error || 'unavailable',
            rawText: res.rawText,
          });
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [selectedVisualAssetId]);

  useEffect(() => {
    if (!selectedTraceRunId) {
      setTraceGraph(null);
      setTraceError(null);
      return;
    }
    const controller = new AbortController();
    fetchJson<DebugGraphData>(`/trace/runs/${selectedTraceRunId}?mode=${traceMode}`, controller.signal)
      .then((res) => {
        if (res.ok) {
          setTraceGraph(res.data);
          setTraceError(null);
        } else {
          setTraceGraph(null);
          setTraceError({
            label: 'trace graph',
            status: res.status,
            error: res.error || 'unavailable',
            rawText: res.rawText,
          });
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [selectedTraceRunId, traceMode]);

  useEffect(() => {
    setSelectedGraphNode(null);
  }, [kgGraph, traceGraph]);

  const loadKgGraph = useCallback(async () => {
    setKgLoading(true);
    const nodeType = kgNodeTypeFilter.trim();
    const limitValue = Number.parseInt(kgLimit, 10);
    const limit = Number.isFinite(limitValue) ? Math.min(Math.max(limitValue, 50), 2000) : 500;
    const query = new URLSearchParams({ limit: String(limit), edge_limit: String(limit * 3) });
    if (nodeType) query.set('node_type', nodeType);
    const res = await fetchJson<DebugGraphData>(`/debug/kg?${query.toString()}`);
    if (res.ok) {
      setKgGraph(res.data);
      setKgError(null);
    } else {
      setKgGraph(null);
      setKgError({
        label: 'kg snapshot',
        status: res.status,
        error: res.error || 'unavailable',
        rawText: res.rawText,
      });
    }
    setKgLoading(false);
  }, [kgLimit, kgNodeTypeFilter]);

  if (view === 'run-inspector' && inspectRunId) {
    return (
      <div className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-6xl rounded-xl border bg-white p-6 shadow-sm">
          <IngestRunInspector
            runId={inspectRunId}
            onBack={() => {
              setView('dashboard');
              setInspectRunId(null);
            }}
          />
        </div>
      </div>
    );
  }

  if (view === 'policy-inspector' && inspectDocId) {
    return (
      <div className="min-h-screen bg-slate-50 p-6">
        <div className="mx-auto max-w-6xl rounded-xl border bg-white p-6 shadow-sm">
          <PolicyInspector
            documentId={inspectDocId}
            onBack={() => {
              setView('dashboard');
              setInspectDocId(null);
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen"
      style={{
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text)',
      }}
    >
      <header className="border-b bg-white shadow-sm">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-text-light)' }}>
              Debug
            </div>
            <h1 className="text-xl font-semibold" style={{ color: 'var(--color-ink)' }}>
              TPA Debug Console
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-text-light)' }}>
              Live snapshot of backend status, ingestion, and schema registry.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => (window.location.href = '/')}
              style={{ borderColor: 'var(--color-neutral-300)', color: 'var(--color-text)' }}
            >
              <ArrowLeft className="h-4 w-4" />
              Back to app
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleResetIngest({ scope: 'running' })}
              style={{ borderColor: 'rgba(234, 88, 12, 0.35)', color: 'var(--color-warning)' }}
            >
              Reset running ingest
            </Button>
            <Button
              size="sm"
              onClick={() => load()}
              disabled={loading}
              style={{ backgroundColor: 'var(--color-brand)', color: 'var(--color-ink)' }}
            >
              <RefreshCcw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 py-6">
        {actionMessage && (
          <div
            className="mb-4 rounded-lg border px-4 py-2 text-sm"
            style={{ borderColor: 'var(--color-neutral-300)', backgroundColor: 'rgba(15, 23, 42, 0.04)' }}
          >
            {actionMessage}
          </div>
        )}
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>API status</CardTitle>
              <CardDescription>Health + readiness probes (same endpoints the platform uses).</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span>Environment</span>
                <StatusBadge label={envLabel} />
              </div>
              <div className="flex items-center justify-between">
                <span>/healthz</span>
                <StatusBadge label={health?.status || 'unknown'} />
              </div>
              <div className="flex items-center justify-between">
                <span>/readyz</span>
                <StatusBadge label={ready?.status || ready?.db || 'unknown'} />
              </div>
              <div className="flex items-center justify-between">
                <span>Last updated</span>
                <span>{lastUpdated || '--'}</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>API quick links</CardTitle>
              <CardDescription>Handy endpoints for deeper inspection.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span>/api/docs</span>
                <a className="text-sm underline" href="/api/docs" target="_blank" rel="noreferrer">
                  Open
                </a>
              </div>
              <div className="flex items-center justify-between">
                <span>/api/ingest/jobs</span>
                <a className="text-sm underline" href="/api/ingest/jobs" target="_blank" rel="noreferrer">
                  Open
                </a>
              </div>
              <div className="flex items-center justify-between">
                <span>/api/ingest/batches</span>
                <a className="text-sm underline" href="/api/ingest/batches" target="_blank" rel="noreferrer">
                  Open
                </a>
              </div>
              <div className="flex items-center justify-between">
                <span>/api/spec/schemas</span>
                <a className="text-sm underline" href="/api/spec/schemas" target="_blank" rel="noreferrer">
                  Open
                </a>
              </div>
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Manual Ingest</CardTitle>
              <CardDescription>Upload a PDF to trigger a debug ingest run.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-2">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept="application/pdf"
                  style={{ display: 'none' }}
                />
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="w-full"
                  style={{ backgroundColor: 'var(--color-brand)', color: 'var(--color-ink)' }}
                >
                  {uploading ? (
                    <RefreshCcw className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="mr-2 h-4 w-4" />
                  )}
                  {uploading ? 'Uploading...' : 'Upload & Ingest'}
                </Button>
                <p className="text-xs text-slate-500">
                  Uploaded file will be saved to authority_packs/debug and a new run will start immediately.
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Coverage overview</CardTitle>
              <CardDescription>Snapshot counts across the pipeline.</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 text-sm">
              {(overview?.counts
                ? Object.entries(overview.counts)
                : []
              ).map(([key, value]) => (
                <div key={key} className="rounded-lg border px-3 py-2" style={{ borderColor: 'var(--color-neutral-300)' }}>
                  <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-light)' }}>
                    {key.replace(/_/g, ' ')}
                  </div>
                  <div className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
                    {value}
                  </div>
                </div>
              ))}
              {!overview?.counts && <span>No overview data yet.</span>}
            </CardContent>
          </Card>
        </div>

        {endpointErrors.length > 0 && (
          <div
            className="mt-6 rounded-xl border px-4 py-3 text-sm"
            style={{ borderColor: 'rgba(234, 88, 12, 0.35)', backgroundColor: 'rgba(234, 88, 12, 0.08)' }}
          >
            <div className="flex items-center gap-2 font-medium" style={{ color: 'var(--color-warning)' }}>
              <AlertTriangle className="h-4 w-4" />
              {endpointErrors.length} backend checks failed
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {endpointErrors.map((error) => (
                <li key={`${error.label}-${error.status}`}>
                  <div className="font-medium">
                    {error.label} {error.status ? `(${error.status})` : ''}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--color-text-light)' }}>
                    {error.error}
                  </div>
                  {error.rawText && error.rawText !== error.error && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs" style={{ color: 'var(--color-text-light)' }}>
                        Response body
                      </summary>
                      <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs">{error.rawText}</pre>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <Separator className="my-8" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Latest ingest jobs</CardTitle>
              <CardDescription>Most recent background jobs from the ingest worker.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Job</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Authority</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Error</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6}>No ingest jobs found.</TableCell>
                    </TableRow>
                  ) : (
                    jobs.map((job) => (
                      <TableRow key={job.ingest_job_id}>
                        <TableCell className="font-mono text-xs">{job.ingest_job_id.slice(0, 8)}</TableCell>
                        <TableCell>
                          <StatusBadge label={job.status || 'unknown'} />
                        </TableCell>
                        <TableCell>{job.authority_id || '--'}</TableCell>
                        <TableCell>{formatDate(job.created_at)}</TableCell>
                        <TableCell className="max-w-[160px] truncate text-xs" title={job.error_text || ''}>
                          {job.error_text || '--'}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleResetIngest({ ingest_job_id: job.ingest_job_id })}
                            >
                              Reset
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => handleRequeueJob(job.ingest_job_id)}>
                              Requeue
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Latest ingest batches</CardTitle>
              <CardDescription>Recent ingest batches and their runtime window.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Batch</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Authority</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {batches.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>No ingest batches found.</TableCell>
                    </TableRow>
                  ) : (
                    batches.map((batch) => (
                      <TableRow key={batch.ingest_batch_id}>
                        <TableCell className="font-mono text-xs">{batch.ingest_batch_id.slice(0, 8)}</TableCell>
                        <TableCell>
                          <StatusBadge label={batch.status || 'unknown'} />
                        </TableCell>
                        <TableCell>{batch.authority_id || '--'}</TableCell>
                        <TableCell>{formatDate(batch.started_at)}</TableCell>
                        <TableCell>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleResetIngest({ ingest_batch_id: batch.ingest_batch_id })}
                          >
                            Reset
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <Separator className="my-8" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Ingest runs</CardTitle>
              <CardDescription>Pipeline executions (click to inspect steps).</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead></TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ingestRuns.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>No ingest runs found.</TableCell>
                    </TableRow>
                  ) : (
                    ingestRuns.map((run) => (
                      <TableRow
                        key={run.id}
                        className={selectedIngestRunId === run.id ? 'bg-slate-50' : undefined}
                        onClick={() => setSelectedIngestRunId(run.id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <TableCell className="font-mono text-xs">{run.id.slice(0, 8)}</TableCell>
                        <TableCell>
                          <StatusBadge label={run.status || 'unknown'} />
                        </TableCell>
                        <TableCell>{formatDate(run.started_at)}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              setInspectRunId(run.id);
                              setView('run-inspector');
                            }}
                          >
                            <Search className="h-4 w-4" />
                          </Button>
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleResetIngest({ run_id: run.id });
                            }}
                          >
                            Reset
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Run steps</CardTitle>
              <CardDescription>Step status and timing for the selected run.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Step</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ingestRunSteps.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4}>Select a run to view steps.</TableCell>
                    </TableRow>
                  ) : (
                    ingestRunSteps.map((step) => (
                      <TableRow
                        key={step.id}
                        className={selectedRunStepId === step.id ? 'bg-slate-50' : undefined}
                        onClick={() => setSelectedRunStepId(step.id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <TableCell className="text-xs">{step.step_name}</TableCell>
                        <TableCell>
                          <StatusBadge label={step.status || 'unknown'} />
                        </TableCell>
                        <TableCell>{formatDate(step.started_at)}</TableCell>
                        <TableCell className="max-w-[160px] truncate text-xs" title={step.error_text || ''}>
                          {step.error_text || '--'}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
              {selectedRunStep && (
                <div className="mt-4 rounded-lg border p-3 text-xs" style={{ borderColor: 'var(--color-neutral-300)' }}>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-text-light)' }}>
                    Step detail
                  </div>
                  <pre className="whitespace-pre-wrap text-[11px] leading-relaxed">
                    {JSON.stringify(
                      {
                        step_name: selectedRunStep.step_name,
                        status: selectedRunStep.status,
                        error_text: selectedRunStep.error_text,
                        inputs: selectedRunStep.inputs_jsonb,
                        outputs: selectedRunStep.outputs_jsonb,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Separator className="my-8" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
              <CardDescription>Parsed documents (click to load coverage).</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Doc</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3}>No documents found.</TableCell>
                    </TableRow>
                  ) : (
                    documents.map((doc) => (
                      <TableRow
                        key={doc.id}
                        className={selectedDocumentId === doc.id ? 'bg-slate-50' : undefined}
                        onClick={() => setSelectedDocumentId(doc.id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <TableCell className="font-mono text-xs">{doc.id.slice(0, 8)}</TableCell>
                        <TableCell className="text-xs">{doc.title || 'Untitled document'}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              setInspectDocId(doc.id);
                              setView('policy-inspector');
                            }}
                          >
                            <FileText className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Document coverage</CardTitle>
              <CardDescription>Counts + assertions for the selected document.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {documentCoverageError ? (
                <div
                  className="rounded-lg border px-3 py-2 text-xs"
                  style={{ borderColor: 'rgba(234, 88, 12, 0.35)', backgroundColor: 'rgba(234, 88, 12, 0.08)' }}
                >
                  <div className="font-semibold">
                    {documentCoverageError.label} {documentCoverageError.status ? `(${documentCoverageError.status})` : ''}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--color-text-light)' }}>
                    {documentCoverageError.error}
                  </div>
                  {documentCoverageError.rawText && documentCoverageError.rawText !== documentCoverageError.error && (
                    <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[11px]">{documentCoverageError.rawText}</pre>
                  )}
                </div>
              ) : !documentCoverage ? (
                <div>Select a document to view coverage.</div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(documentCoverage.counts || {}).map(([key, value]) => (
                      <div key={key} className="rounded border px-3 py-2" style={{ borderColor: 'var(--color-neutral-300)' }}>
                        <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-light)' }}>
                          {key.replace(/_/g, ' ')}
                        </div>
                        <div className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
                          {value}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="space-y-2">
                    {(documentCoverage.assertions || []).map((assertion) => (
                      <div
                        key={assertion.check}
                        className="rounded border px-3 py-2"
                        style={{ borderColor: 'var(--color-neutral-300)' }}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold uppercase tracking-[0.12em]">
                            {assertion.check.replace(/_/g, ' ')}
                          </span>
                          <StatusBadge label={assertion.ok ? 'ok' : 'missing'} />
                        </div>
                        <div className="text-xs text-slate-500">{assertion.detail}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        <Separator className="my-8" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Tool runs</CardTitle>
              <CardDescription>Recent model/tool invocations.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tool</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Started</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {toolRuns.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3}>No tool runs found.</TableCell>
                    </TableRow>
                  ) : (
                    toolRuns.map((run) => (
                      <TableRow
                        key={run.id}
                        className={selectedToolRunId === run.id ? 'bg-slate-50' : undefined}
                        onClick={() => setSelectedToolRunId(run.id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <TableCell className="text-xs">{run.tool_name || 'tool'}</TableCell>
                        <TableCell>
                          <StatusBadge label={run.status || 'unknown'} />
                        </TableCell>
                        <TableCell>{formatDate(run.started_at)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
              <div className="mt-6">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-text-light)' }}>
                  Georef attempts
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Asset</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Started</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {georefRuns.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3}>No georef attempts logged.</TableCell>
                      </TableRow>
                    ) : (
                      georefRuns.map((run) => (
                        <TableRow
                          key={run.id}
                          className={selectedToolRunId === run.id ? 'bg-slate-50' : undefined}
                          onClick={() => setSelectedToolRunId(run.id)}
                          style={{ cursor: 'pointer' }}
                        >
                          <TableCell className="text-xs font-mono">{run.id.slice(0, 8)}</TableCell>
                          <TableCell>
                            <StatusBadge label={run.status || 'unknown'} />
                          </TableCell>
                          <TableCell>{formatDate(run.started_at)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
              {selectedToolRun && (
                <div className="mt-4 rounded-lg border p-3 text-xs" style={{ borderColor: 'var(--color-neutral-300)' }}>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-text-light)' }}>
                    Tool run detail
                  </div>
                  <pre className="whitespace-pre-wrap text-[11px] leading-relaxed">
                    {JSON.stringify(
                      {
                        tool_name: selectedToolRun.tool_name,
                        status: selectedToolRun.status,
                        confidence_hint: selectedToolRun.confidence_hint,
                        uncertainty_note: selectedToolRun.uncertainty_note,
                        inputs: selectedToolRun.inputs_logged,
                        outputs: selectedToolRun.outputs_logged,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardHeader>
              <CardTitle>Prompt registry</CardTitle>
              <CardDescription>Tracked prompt IDs and latest versions.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Prompt</TableHead>
                    <TableHead>Latest</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {prompts.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3}>No prompts recorded.</TableCell>
                    </TableRow>
                  ) : (
                    prompts.map((prompt) => (
                      <TableRow key={prompt.prompt_id}>
                        <TableCell className="text-xs">{prompt.prompt_id}</TableCell>
                        <TableCell>{latestPromptVersion.get(prompt.prompt_id) ?? '--'}</TableCell>
                        <TableCell>{formatDate(prompt.created_at)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <Separator className="my-8" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

        <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
          <CardHeader>
            <CardTitle>Graph inspector</CardTitle>
            <CardDescription>3D trace + knowledge graph with selection drill-down.</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="kg">
              <TabsList>
                <TabsTrigger value="kg">Knowledge graph</TabsTrigger>
                <TabsTrigger value="trace">Trace graph</TabsTrigger>
              </TabsList>

              <TabsContent value="kg">
                <div className="mb-4 grid gap-3 md:grid-cols-[1fr_auto_auto]">
                  <Input
                    value={kgNodeTypeFilter}
                    onChange={(e) => setKgNodeTypeFilter(e.target.value)}
                    placeholder="Filter by node_type (optional)"
                  />
                  <Input
                    value={kgLimit}
                    onChange={(e) => setKgLimit(e.target.value)}
                    placeholder="Node limit"
                  />
                  <Button
                    onClick={loadKgGraph}
                    disabled={kgLoading}
                    style={{ backgroundColor: 'var(--color-brand)', color: 'var(--color-ink)' }}
                  >
                    {kgLoading ? 'Loading…' : 'Load graph'}
                  </Button>
                </div>
                {kgError && (
                  <div
                    className="mb-4 rounded-lg border px-3 py-2 text-xs"
                    style={{ borderColor: 'rgba(234, 88, 12, 0.35)', backgroundColor: 'rgba(234, 88, 12, 0.08)' }}
                  >
                    <div className="font-semibold">
                      {kgError.label} {kgError.status ? `(${kgError.status})` : ''}
                    </div>
                    <div className="text-xs" style={{ color: 'var(--color-text-light)' }}>
                      {kgError.error}
                    </div>
                    {kgError.rawText && kgError.rawText !== kgError.error && (
                      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[11px]">{kgError.rawText}</pre>
                    )}
                  </div>
                )}
                <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
                  <DebugGraph3D graph={kgGraph} onNodeSelect={setSelectedGraphNode} selectedNodeId={selectedGraphNode?.node_id || null} />
                  <div className="rounded-xl border p-3 text-xs" style={{ borderColor: 'var(--color-neutral-300)' }}>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-text-light)' }}>
                      Selection
                    </div>
                    {selectedGraphNode ? (
                      <pre className="whitespace-pre-wrap text-[11px] leading-relaxed">
                        {JSON.stringify(selectedGraphNode, null, 2)}
                      </pre>
                    ) : (
                      <div className="text-slate-500">Select a node to inspect.</div>
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="trace">
                <div className="mb-4 grid gap-3 md:grid-cols-[1fr_auto]">
                  <select
                    value={selectedTraceRunId || ''}
                    onChange={(e) => setSelectedTraceRunId(e.target.value || null)}
                    className="flex h-10 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                  >
                    <option value="">Select a run...</option>
                    {traceRuns.map((run) => (
                      <option key={run.id} value={run.id}>
                        {run.id.slice(0, 8)} · {run.culp_stage_id || run.profile || 'run'}
                      </option>
                    ))}
                  </select>
                  <select
                    value={traceMode}
                    onChange={(e) => setTraceMode(e.target.value as 'summary' | 'inspect' | 'forensic')}
                    className="flex h-10 rounded-md border border-input bg-white px-3 py-2 text-sm"
                  >
                    <option value="summary">summary</option>
                    <option value="inspect">inspect</option>
                    <option value="forensic">forensic</option>
                  </select>
                </div>
                {traceError && (
                  <div
                    className="mb-4 rounded-lg border px-3 py-2 text-xs"
                    style={{ borderColor: 'rgba(234, 88, 12, 0.35)', backgroundColor: 'rgba(234, 88, 12, 0.08)' }}
                  >
                    <div className="font-semibold">
                      {traceError.label} {traceError.status ? `(${traceError.status})` : ''}
                    </div>
                    <div className="text-xs" style={{ color: 'var(--color-text-light)' }}>
                      {traceError.error}
                    </div>
                    {traceError.rawText && traceError.rawText !== traceError.error && (
                      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[11px]">{traceError.rawText}</pre>
                    )}
                  </div>
                )}
                <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
                  <DebugGraph3D graph={traceGraph} onNodeSelect={setSelectedGraphNode} selectedNodeId={selectedGraphNode?.node_id || null} />
                  <div className="rounded-xl border p-3 text-xs" style={{ borderColor: 'var(--color-neutral-300)' }}>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-text-light)' }}>
                      Selection
                    </div>
                    {selectedGraphNode ? (
                      <pre className="whitespace-pre-wrap text-[11px] leading-relaxed">
                        {JSON.stringify(selectedGraphNode, null, 2)}
                      </pre>
                    ) : (
                      <div className="text-slate-500">Select a node to inspect.</div>
                    )}
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <Separator className="my-8" style={{ backgroundColor: 'var(--color-neutral-300)' }} />

        <Card className="border" style={{ borderColor: 'var(--color-neutral-300)' }}>
          <CardHeader>
            <CardTitle>Schema registry</CardTitle>
            <CardDescription>{schemas.length} schemas loaded from the spec root.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {schemas.length === 0 ? (
              <span>No schemas found.</span>
            ) : (
              schemas.map((schema) => (
                <Badge
                  key={schema}
                  variant="outline"
                  className="font-mono text-xs"
                  style={{ borderColor: 'var(--color-neutral-300)', color: 'var(--color-text)' }}
                >
                  {schema}
                </Badge>
              ))
            )}
          </CardContent>
        </Card>

        {loading && (
          <div className="mt-6 flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-light)' }}>
            <RefreshCcw className="h-4 w-4 animate-spin" />
            Refreshing debug data...
          </div>
        )}
      </main>
    </div>
  );
}

export function DebugDisabled() {
  return (
    <div
      className="flex min-h-screen items-center justify-center px-6 text-center"
      style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text)' }}
    >
      <div className="max-w-md">
        <div className="flex items-center justify-center gap-2 text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
          <CheckCircle2 className="h-5 w-5" />
          Debug console disabled
        </div>
        <p className="mt-2 text-sm" style={{ color: 'var(--color-text-light)' }}>
          The debug route is only available in development builds. Start the UI dev container to enable it.
        </p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => (window.location.href = '/')}
          style={{ borderColor: 'var(--color-neutral-300)', color: 'var(--color-text)' }}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to app
        </Button>
      </div>
    </div>
  );
}
