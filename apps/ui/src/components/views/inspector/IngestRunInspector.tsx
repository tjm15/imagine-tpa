import { useEffect, useState } from 'react';
import { ArrowLeft, CheckCircle2, Clock, AlertTriangle, FileText, Database, Layers } from 'lucide-react';
import { Button } from '../../ui/button';
import { Badge } from '../../ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../ui/card';
import { Separator } from '../../ui/separator';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../ui/table';

type DeepRunData = {
  run: {
    id: string;
    ingest_batch_id?: string;
    status: string;
    started_at: string;
    ended_at?: string;
    error_text?: string;
    model_ids_jsonb?: Record<string, string>;
  };
  steps: Array<{
    step_name: string;
    status: string;
    started_at: string;
    ended_at?: string;
    error_text?: string;
  }>;
  tool_runs: Array<{
    id: string;
    tool_name: string;
    status: string;
    started_at: string;
    ended_at?: string;
    confidence_hint?: string;
    error_detail?: string;
  }>;
  output_counts: Record<string, number>;
};

export function IngestRunInspector({ runId, onBack }: { runId: string; onBack: () => void }) {
  const [data, setData] = useState<DeepRunData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/debug/ingest/runs/${runId}/deep`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch run details');
        return res.json();
      })
      .then(setData)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <div className="p-8 text-center">Loading run details...</div>;
  if (error) return <div className="p-8 text-center text-red-600">Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="outline" size="sm" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <div>
          <h2 className="text-xl font-semibold">Ingest Run Inspector</h2>
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="font-mono">{data.run.id.slice(0, 8)}</span>
            <span>•</span>
            <span>{new Date(data.run.started_at).toLocaleString()}</span>
          </div>
        </div>
        <div className="ml-auto">
          <Badge variant={data.run.status === 'success' ? 'default' : 'destructive'}>
            {data.run.status}
          </Badge>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Artifacts Generated</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col">
                <span className="text-2xl font-bold">{data.output_counts.layout_blocks}</span>
                <span className="text-xs text-slate-500">Text Blocks</span>
              </div>
              <div className="flex flex-col">
                <span className="text-2xl font-bold">{data.output_counts.visual_assets}</span>
                <span className="text-xs text-slate-500">Visual Assets</span>
              </div>
              <div className="flex flex-col">
                <span className="text-2xl font-bold">{data.output_counts.policy_sections}</span>
                <span className="text-xs text-slate-500">Policy Sections</span>
              </div>
              <div className="flex flex-col">
                <span className="text-2xl font-bold">{data.output_counts.vectors}</span>
                <span className="text-xs text-slate-500">Embeddings</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Model Usage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            {Object.entries(data.run.model_ids_jsonb || {}).map(([key, model]) => (
              <div key={key} className="flex justify-between">
                <span className="text-slate-500">{key.replace('_id', '').replace(/_/g, ' ')}</span>
                <span className="font-mono">{model}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Timing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.steps.map((step) => {
              const duration = step.ended_at
                ? (new Date(step.ended_at).getTime() - new Date(step.started_at).getTime()) / 1000
                : null;
              return (
                <div key={step.step_name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <div
                      className={`h-2 w-2 rounded-full ${
                        step.status === 'success' ? 'bg-green-500' : 'bg-amber-500'
                      }`}
                    />
                    <span>{step.step_name}</span>
                  </div>
                  <span className="font-mono text-slate-500">
                    {duration ? `${duration.toFixed(1)}s` : '...'}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>

      <Separator />

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Tool Execution Log</h3>
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tool</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Time</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Error / Note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.tool_runs.map((run) => (
                <TableRow key={run.id}>
                  <TableCell className="font-medium">{run.tool_name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={run.status === 'success' ? 'border-green-500 text-green-600' : 'border-red-500 text-red-600'}>
                      {run.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-slate-500">
                    {new Date(run.started_at).toLocaleTimeString()}
                  </TableCell>
                  <TableCell>
                    {run.confidence_hint && (
                      <Badge variant="secondary">{run.confidence_hint}</Badge>
                    )}
                  </TableCell>
                  <TableCell className="max-w-md truncate text-xs text-slate-500" title={run.error_detail || ''}>
                    {run.error_detail || run.uncertainty_note || '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </div>
    </div>
  );
}
