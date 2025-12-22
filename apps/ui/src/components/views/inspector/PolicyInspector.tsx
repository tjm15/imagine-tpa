import { useEffect, useState } from 'react';
import { ArrowLeft, BookOpen, Table as TableIcon, List, Eye } from 'lucide-react';
import { Button } from '../../ui/button';
import { Badge } from '../../ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../ui/tabs';
import { ScrollArea } from '../../ui/scroll-area';

type PolicyData = {
  sections: Array<{
    id: string;
    policy_code: string;
    title: string;
    text: string;
  }>;
  clauses: Array<{
    id: string;
    policy_section_id: string;
    clause_ref: string;
    text: string;
    conditions_jsonb?: Array<{ operator: string; trigger_text: string }>;
  }>;
  matrices: Array<{
    id: string;
    matrix_jsonb: {
      matrix_id: string;
      logic_type: string;
      inputs: string[];
      outputs: string[];
    };
  }>;
  scopes: Array<{
    id: string;
    scope_jsonb: {
      scope_id: string;
      geography_refs: string[];
      development_types: string[];
    };
  }>;
};

export function PolicyInspector({ documentId, onBack }: { documentId: string; onBack: () => void }) {
  const [data, setData] = useState<PolicyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/debug/policies/${documentId}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch policy structure');
        return res.json();
      })
      .then(setData)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [documentId]);

  if (loading) return <div className="p-8 text-center">Loading policies...</div>;
  if (error) return <div className="p-8 text-center text-red-600">Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="flex h-full flex-col space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="outline" size="sm" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <div>
          <h2 className="text-xl font-semibold">Policy Logic Inspector</h2>
          <div className="text-sm text-slate-500">Document ID: {documentId.slice(0, 8)}</div>
        </div>
      </div>

      <Tabs defaultValue="structure" className="flex-1">
        <TabsList>
          <TabsTrigger value="structure">
            <BookOpen className="mr-2 h-4 w-4" /> Structure
          </TabsTrigger>
          <TabsTrigger value="matrices">
            <TableIcon className="mr-2 h-4 w-4" /> Matrices ({data.matrices.length})
          </TabsTrigger>
          <TabsTrigger value="scopes">
            <Eye className="mr-2 h-4 w-4" /> Scopes ({data.scopes.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="structure" className="mt-4 h-[calc(100vh-200px)]">
          <ScrollArea className="h-full pr-4">
            <div className="space-y-6">
              {data.sections.map((section) => (
                <Card key={section.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">
                        {section.policy_code}: {section.title}
                      </CardTitle>
                      <Badge variant="outline">Section</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 pt-2">
                    <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
                      {section.text}
                    </div>
                    
                    <div className="space-y-2 pl-4 border-l-2 border-slate-200">
                      {data.clauses
                        .filter((c) => c.policy_section_id === section.id)
                        .map((clause) => (
                          <div key={clause.id} className="text-sm">
                            <span className="font-semibold text-slate-900">{clause.clause_ref}</span>
                            <span className="ml-2 text-slate-600">{clause.text}</span>
                            {clause.conditions_jsonb && clause.conditions_jsonb.length > 0 && (
                              <div className="mt-1 flex gap-2">
                                {clause.conditions_jsonb.map((cond, i) => (
                                  <Badge key={i} variant="secondary" className="text-[10px]">
                                    {cond.operator}: {cond.trigger_text}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="matrices" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            {data.matrices.map((matrix) => (
              <Card key={matrix.id}>
                <CardHeader>
                  <CardTitle className="text-sm font-mono">
                    {matrix.matrix_jsonb.matrix_id}
                  </CardTitle>
                  <Badge>{matrix.matrix_jsonb.logic_type}</Badge>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div>
                      <span className="font-semibold">Inputs:</span>{' '}
                      {matrix.matrix_jsonb.inputs.join(', ')}
                    </div>
                    <div>
                      <span className="font-semibold">Outputs:</span>{' '}
                      {matrix.matrix_jsonb.outputs.join(', ')}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="scopes" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            {data.scopes.map((scope) => (
              <Card key={scope.id}>
                <CardHeader>
                  <CardTitle className="text-sm font-mono">
                    {scope.scope_jsonb.scope_id}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {scope.scope_jsonb.geography_refs?.length > 0 && (
                    <div>
                      <span className="font-semibold">Geography:</span>{' '}
                      {scope.scope_jsonb.geography_refs.join(', ')}
                    </div>
                  )}
                  {scope.scope_jsonb.development_types?.length > 0 && (
                    <div>
                      <span className="font-semibold">Dev Types:</span>{' '}
                      {scope.scope_jsonb.development_types.join(', ')}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
