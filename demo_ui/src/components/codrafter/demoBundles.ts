import type { PatchBundle } from './types';

function formatBundleId(seq: number) {
  return `PB-${String(seq).padStart(3, '0')}`;
}

export function createDemoPatchBundle(params: { seq: number; stageId: string }): PatchBundle {
  const now = new Date().toISOString();
  const id = formatBundleId(params.seq);

  if (params.stageId === 'baseline') {
    return {
      id,
      title: 'Make transport limitations explicit + flag evidence currency',
      rationale:
        'DfT Connectivity outputs are referenced without limitations; make caveats explicit, link the evidence item, and register a monitoring signal for the next gateway.',
      createdAt: now,
      severity: 'attention',
      confidence: 'high',
      status: 'proposed',
      items: [
        {
          id: `${id}-IT-01`,
          type: 'policy_text',
          title: 'Add baseline limitations note (Transport & Connectivity)',
          artefactLabel: 'Deliverable · Place Portrait (Baseline Evidence)',
          before:
            '“Cambridge benefits from strong rail connectivity… However, strategic road capacity remains constrained…”',
          after:
            'Adds: “Limitations: DfT connectivity outputs do not model capacity constraints or future growth scenarios; treat results as indicative only.”',
          traceTarget: { kind: 'evidence', id: 'ev-transport-dft', label: 'DfT Connectivity Tool output (demo)' },
        },
        {
          id: `${id}-IT-02`,
          type: 'evidence_links',
          title: 'Link DfT Connectivity Tool evidence',
          artefactLabel: 'Evidence · DfT Connectivity Tool (2024)',
          before: 'Transport baseline paragraph has 0 linked evidence items.',
          after: 'Adds evidence link: ev-transport-dft (citable).',
          traceTarget: { kind: 'evidence', id: 'ev-transport-dft', label: 'DfT Connectivity Tool output (demo)' },
        },
        {
          id: `${id}-IT-03`,
          type: 'allocation_geometry',
          title: 'Trim SHLAA/045 boundary away from Conservation Area',
          artefactLabel: 'Allocation · SHLAA/045 Northern Fringe',
          siteId: 'SHLAA/045',
          before: 'Boundary overlaps Conservation Area by ~0.3ha (demo).',
          after: 'Boundary trimmed to reduce heritage harm; retains capacity assumption (demo).',
          traceTarget: { kind: 'site', id: 'SHLAA/045', label: 'SHLAA/045 Northern Fringe' },
        },
        {
          id: `${id}-IT-04`,
          type: 'issue_update',
          title: 'Register monitoring signal (gateway readiness)',
          artefactLabel: 'Monitoring · Gateway readiness',
          before: 'No signal registered for transport baseline currency.',
          after: 'Adds signal: “Transport baseline evidence currency – action required before Gateway 1”.',
          traceTarget: { kind: 'ai_hint', id: 'gateway-transport-currency', label: 'Gateway readiness signal (demo)' },
        },
      ],
    };
  }

  return {
    id,
    title: 'Draft patch bundle (demo)',
    rationale:
      'Placeholder patch bundle for this stage. Extend `createDemoPatchBundle` per stage to model policy, spatial, evidence, and monitoring updates.',
    createdAt: now,
    severity: 'info',
    confidence: 'medium',
    status: 'proposed',
    items: [
      {
        id: `${id}-IT-01`,
        type: 'issue_update',
        title: 'Register an issue for follow-up',
        artefactLabel: 'Issues · Register',
        before: 'No issue recorded.',
        after: 'Issue created (demo).',
        traceTarget: { kind: 'run', label: 'Current run' },
      },
    ],
  };
}

