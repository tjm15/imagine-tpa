import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, RefreshCcw, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';

type ApiResult<T> = {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
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

const API_PREFIX = '/api';

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
      };
    }
    return { ok: true, status: resp.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: null, error: String((err as Error).message || err) };
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
  const [errors, setErrors] = useState<string[]>([]);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [ready, setReady] = useState<HealthPayload | null>(null);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [batches, setBatches] = useState<IngestBatch[]>([]);
  const [schemas, setSchemas] = useState<string[]>([]);

  const envLabel = useMemo(() => (import.meta.env.DEV ? 'dev' : 'prod'), []);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setErrors([]);
    const [healthRes, readyRes, jobsRes, batchesRes, schemasRes] = await Promise.all([
      fetchJson<HealthPayload>('/healthz', signal),
      fetchJson<HealthPayload>('/readyz', signal),
      fetchJson<{ ingest_jobs: IngestJob[] }>('/ingest/jobs?limit=10', signal),
      fetchJson<{ ingest_batches: IngestBatch[] }>('/ingest/batches?limit=10', signal),
      fetchJson<{ schemas: string[] }>('/spec/schemas', signal),
    ]);

    const nextErrors: string[] = [];
    if (!healthRes.ok) nextErrors.push(`healthz: ${healthRes.error || 'unavailable'}`);
    if (!readyRes.ok) nextErrors.push(`readyz: ${readyRes.error || 'unavailable'}`);
    if (!jobsRes.ok) nextErrors.push(`ingest jobs: ${jobsRes.error || 'unavailable'}`);
    if (!batchesRes.ok) nextErrors.push(`ingest batches: ${batchesRes.error || 'unavailable'}`);
    if (!schemasRes.ok) nextErrors.push(`schemas: ${schemasRes.error || 'unavailable'}`);

    setHealth(healthRes.data);
    setReady(readyRes.data);
    setJobs(jobsRes.data?.ingest_jobs || []);
    setBatches(batchesRes.data?.ingest_batches || []);
    setSchemas(schemasRes.data?.schemas || []);
    setErrors(nextErrors);
    setLastUpdated(new Date().toLocaleString());
    setLoading(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

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
        <div className="grid gap-6 lg:grid-cols-2">
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
        </div>

        {errors.length > 0 && (
          <div
            className="mt-6 rounded-xl border px-4 py-3 text-sm"
            style={{ borderColor: 'rgba(234, 88, 12, 0.35)', backgroundColor: 'rgba(234, 88, 12, 0.08)' }}
          >
            <div className="flex items-center gap-2 font-medium" style={{ color: 'var(--color-warning)' }}>
              <AlertTriangle className="h-4 w-4" />
              {errors.length} backend checks failed
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {errors.map((error) => (
                <li key={error}>{error}</li>
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
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4}>No ingest jobs found.</TableCell>
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
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {batches.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4}>No ingest batches found.</TableCell>
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
