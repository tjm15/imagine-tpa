/**
 * Mock Data Fixtures for Planner-First UX Testbed
 * 
 * These fixtures provide realistic planning data for demonstration
 * and iteration without backend dependencies.
 */

// ============================================================================
// AUTHORITIES & PROJECTS
// ============================================================================

export interface Authority {
  id: string;
  name: string;
  region: string;
  type: 'district' | 'county' | 'unitary' | 'london_borough' | 'metropolitan';
}

export interface PlanProject {
  id: string;
  authorityId: string;
  name: string;
  type: 'local_plan' | 'neighbourhood_plan' | 'area_action_plan';
  stage: CulpStage;
  startDate: string;
  targetAdoption: string;
}

export interface CulpStage {
  id: string;
  name: string;
  status: 'complete' | 'in-progress' | 'blocked' | 'not-started';
  dueDate: string;
  blockers?: string[];
  requiredArtefacts: string[];
  completedArtefacts: string[];
}

export interface Application {
  id: string;
  reference: string;
  authorityId: string;
  address: string;
  ward: string;
  description: string;
  applicant: string;
  agent?: string;
  status: 'validation' | 'consultation' | 'assessment' | 'determination' | 'decided';
  daysRemaining: number;
  receivedDate: string;
  targetDate: string;
}

// Sample data
export const mockAuthorities: Authority[] = [
  {
    id: 'cambridge',
    name: 'Cambridge City Council',
    region: 'East of England',
    type: 'district'
  },
  {
    id: 'south-cambs',
    name: 'South Cambridgeshire District Council',
    region: 'East of England',
    type: 'district'
  }
];

export const mockCulpStages: CulpStage[] = [
  {
    id: 'notice-boundary',
    name: 'Notice & Boundary',
    status: 'complete',
    dueDate: '2025-01-15',
    requiredArtefacts: ['boundary_map', 'public_notice'],
    completedArtefacts: ['boundary_map', 'public_notice']
  },
  {
    id: 'timetable',
    name: 'Timetable Published',
    status: 'complete',
    dueDate: '2025-02-01',
    requiredArtefacts: ['lds_update', 'timetable_published'],
    completedArtefacts: ['lds_update', 'timetable_published']
  },
  {
    id: 'gateway-1',
    name: 'Gateway 1',
    status: 'complete',
    dueDate: '2025-03-15',
    requiredArtefacts: ['gateway1_submission', 'sea_screening'],
    completedArtefacts: ['gateway1_submission', 'sea_screening']
  },
  {
    id: 'baseline',
    name: 'Baseline & Place Portrait',
    status: 'in-progress',
    dueDate: '2025-06-30',
    blockers: ['Transport baseline incomplete - awaiting DfT data'],
    requiredArtefacts: ['place_portrait', 'housing_baseline', 'transport_baseline', 'environment_baseline'],
    completedArtefacts: ['place_portrait', 'housing_baseline']
  },
  {
    id: 'vision',
    name: 'Vision & Outcomes',
    status: 'not-started',
    dueDate: '2025-07-31',
    requiredArtefacts: ['vision_statement', 'outcomes_framework'],
    completedArtefacts: []
  },
  {
    id: 'sites-identify',
    name: 'Sites Stage 1: Identify',
    status: 'not-started',
    dueDate: '2025-09-30',
    requiredArtefacts: ['call_for_sites', 'site_register'],
    completedArtefacts: []
  },
  {
    id: 'sites-assess',
    name: 'Sites Stage 2: Assess',
    status: 'not-started',
    dueDate: '2025-12-31',
    requiredArtefacts: ['site_assessments', 'shortlist'],
    completedArtefacts: []
  },
  {
    id: 'gateway-2',
    name: 'Gateway 2',
    status: 'not-started',
    dueDate: '2026-02-28',
    requiredArtefacts: ['reg18_draft', 'gateway2_submission'],
    completedArtefacts: []
  }
];

export const mockPlanProject: PlanProject = {
  id: 'cambridge-2025',
  authorityId: 'cambridge',
  name: 'Cambridge Local Plan 2025',
  type: 'local_plan',
  stage: mockCulpStages[3], // Baseline stage
  startDate: '2024-10-01',
  targetAdoption: '2027-03-31'
};

export const mockApplication: Application = {
  id: 'app-24-0456',
  reference: '24/0456/FUL',
  authorityId: 'cambridge',
  address: '45 Mill Road, Cambridge CB1 2AD',
  ward: 'Petersfield',
  description: 'Change of use from retail (Class E) to residential (2 x 1-bed flats) with internal alterations',
  applicant: 'Mill Road Developments Ltd',
  agent: 'Smith Planning Associates',
  status: 'assessment',
  daysRemaining: 12,
  receivedDate: '2024-11-15',
  targetDate: '2025-01-10'
};

// ============================================================================
// EVIDENCE & POLICY
// ============================================================================

export interface EvidenceCard {
  id: string;
  title: string;
  source: string;
  sourceType: 'official_statistics' | 'commissioned_study' | 'internal_gis' | 'site_visit' | 'consultation' | 'case_law';
  date: string;
  confidence: 'high' | 'medium' | 'low';
  limitations?: string;
  summary?: string;
  dataPoints?: Record<string, string | number>;
  licence?: string;
}

export interface PolicyChip {
  id: string;
  reference: string;
  title: string;
  source: 'local_plan' | 'nppf' | 'case_law' | 'nppg';
  relevance: 'high' | 'medium' | 'low';
  excerpt?: string;
  url?: string;
}

export const mockEvidenceCards: EvidenceCard[] = [
  {
    id: 'ev-census-2021',
    title: 'Census 2021: Housing Stock & Tenure',
    source: 'ONS Census 2021',
    sourceType: 'official_statistics',
    date: '2021-03-21',
    confidence: 'high',
    summary: 'Comprehensive housing stock data for Cambridge authority area.',
    dataPoints: {
      'Total dwellings': 52400,
      'Owner-occupied': '48%',
      'Private rented': '28%',
      'Social rented': '24%'
    },
    licence: 'Open Government Licence v3.0'
  },
  {
    id: 'ev-affordability',
    title: 'Housing Affordability Ratio',
    source: 'ONS House Price Statistics',
    sourceType: 'official_statistics',
    date: '2024-09-30',
    confidence: 'high',
    summary: 'Median house price to median earnings ratio.',
    dataPoints: {
      'Affordability ratio': 12.8,
      'Regional average': 8.2,
      'Change since 2015': '+22%'
    },
    licence: 'Open Government Licence v3.0'
  },
  {
    id: 'ev-shlaa-2024',
    title: 'Strategic Housing Land Availability Assessment 2024',
    source: 'Cambridge City Council',
    sourceType: 'commissioned_study',
    date: '2024-06-15',
    confidence: 'medium',
    limitations: 'Deliverability assumptions require annual review. Some sites await viability testing.',
    summary: 'Assessment of land availability for housing development.',
    dataPoints: {
      'Total capacity (gross)': 14500,
      'Deliverable (0-5yr)': 4200,
      'Developable (6-10yr)': 6800,
      'Constrained': 3500
    }
  },
  {
    id: 'ev-transport-dft',
    title: 'DfT Connectivity Tool Outputs',
    source: 'Department for Transport',
    sourceType: 'official_statistics',
    date: '2024-03-01',
    confidence: 'medium',
    limitations: 'Does not model capacity constraints or local congestion. Shows accessibility, not capacity.',
    summary: 'Journey time accessibility metrics for Cambridge.',
    dataPoints: {
      'Rail to London': '50 mins',
      'Bus coverage (30 min)': '78%',
      'Cycle network km': 142
    },
    licence: 'Open Government Licence v3.0'
  },
  {
    id: 'ev-site-visit',
    title: 'Site Visit Record: 45 Mill Road',
    source: 'Planning Officer',
    sourceType: 'site_visit',
    date: '2024-12-10',
    confidence: 'high',
    summary: 'Officer site visit to assess current condition and context.',
    dataPoints: {
      'Unit status': 'Vacant (12 months+)',
      'Condition': 'Fair, requires internal works',
      'Frontage': '6.2m',
      'Access': 'Direct from Mill Road'
    }
  },
  {
    id: 'ev-marketing',
    title: 'Marketing Evidence: 45 Mill Road',
    source: 'Applicant submission',
    sourceType: 'commissioned_study',
    date: '2024-10-01',
    confidence: 'medium',
    limitations: 'Agent-prepared evidence. Marketing approach and pricing not independently verified.',
    summary: '15 months marketing for retail use without viable interest.',
    dataPoints: {
      'Marketing period': '15 months',
      'Asking rent': '£28/sq ft',
      'Enquiries': 3,
      'Offers received': 0
    }
  }
];

export const mockPolicies: PolicyChip[] = [
  {
    id: 'pol-s1',
    reference: 'LP/2024/S1',
    title: 'Spatial Strategy',
    source: 'local_plan',
    relevance: 'high',
    excerpt: 'Development will be directed to the urban area, with brownfield and previously developed land prioritised.'
  },
  {
    id: 'pol-h1',
    reference: 'LP/2024/H1',
    title: 'Housing Delivery',
    source: 'local_plan',
    relevance: 'high',
    excerpt: 'The Council will seek to deliver a minimum of 1,800 dwellings per annum over the plan period.'
  },
  {
    id: 'pol-t2',
    reference: 'LP/2024/T2',
    title: 'Sustainable Transport',
    source: 'local_plan',
    relevance: 'medium',
    excerpt: 'Development should maximise opportunities for walking, cycling and public transport use.'
  },
  {
    id: 'pol-dm12',
    reference: 'LP/2024/DM12',
    title: 'District Centre Vitality',
    source: 'local_plan',
    relevance: 'high',
    excerpt: 'Ground floor retail uses in District Centres will be protected unless marketing evidence demonstrates no demand over 12 months.'
  },
  {
    id: 'pol-nppf-11',
    reference: 'NPPF para 11',
    title: 'Presumption in Favour of Sustainable Development',
    source: 'nppf',
    relevance: 'high',
    excerpt: 'Plans and decisions should apply a presumption in favour of sustainable development.'
  },
  {
    id: 'pol-nppf-86',
    reference: 'NPPF para 86',
    title: 'Town Centre First',
    source: 'nppf',
    relevance: 'medium',
    excerpt: 'Planning policies and decisions should support the role that town centres play at the heart of local communities.'
  }
];

// ============================================================================
// CONSIDERATIONS & INTERPRETATIONS
// ============================================================================

export interface Interpretation {
  id: string;
  evidenceIds: string[];
  statement: string;
  confidence: 'high' | 'medium' | 'low';
  assumptions?: string[];
  limitations?: string;
  source: 'ai' | 'human';
}

export interface Consideration {
  id: string;
  issue: string;
  interpretationId: string;
  policyIds: string[];
  weight: 'decisive' | 'significant' | 'moderate' | 'limited';
  direction: 'supports' | 'against' | 'neutral';
  settled: boolean;
  tensions?: string[];
  // UI-friendly aliases
  title?: string; // alias for issue
  description?: string;
  summary?: string;
  valence?: 'for' | 'against' | 'neutral'; // alias for direction
  linkedEvidence?: string[];
}

export const mockInterpretations: Interpretation[] = [
  {
    id: 'int-housing-need',
    evidenceIds: ['ev-affordability', 'ev-census-2021'],
    statement: 'The affordability ratio of 12.8x indicates acute housing pressure significantly exceeding regional norms. This represents a deterioration from 10.5x in 2015, suggesting the housing market is becoming increasingly unaffordable for local residents.',
    confidence: 'high',
    source: 'ai'
  },
  {
    id: 'int-delivery-gap',
    evidenceIds: ['ev-shlaa-2024'],
    statement: 'Current identified supply (deliverable + developable) of ~11,000 units falls short of the 27,000 units required over the plan period at 1,800 dpa. Additional site allocations or intensification policies will be needed.',
    confidence: 'medium',
    assumptions: ['Delivery rates remain consistent with 5-year average', 'No major economic shocks'],
    limitations: 'Viability testing not complete for all SHLAA sites.',
    source: 'ai'
  },
  {
    id: 'int-marketing',
    evidenceIds: ['ev-marketing', 'ev-site-visit'],
    statement: 'The marketing evidence demonstrates 15 months of marketing at market rates without viable retail interest, exceeding the 12-month policy requirement. The vacant unit condition and limited footfall context support the conclusion that retail use is not viable at this location.',
    confidence: 'medium',
    assumptions: ['Marketing was conducted at appropriate rent levels', 'Advertising reached relevant market'],
    limitations: 'Marketing approach not independently verified.',
    source: 'ai'
  },
  {
    id: 'int-vitality',
    evidenceIds: ['ev-site-visit'],
    statement: 'The loss of one ground floor retail unit in a District Centre of approximately 45 units would represent a 2.2% reduction. Adjacent units appear to be trading successfully. Overall centre vitality unlikely to be materially harmed.',
    confidence: 'medium',
    assumptions: ['Centre definition includes all units within 200m'],
    source: 'human'
  }
];

export const mockConsiderations: Consideration[] = [
  {
    id: 'con-housing-need',
    issue: 'Housing Need',
    interpretationId: 'int-housing-need',
    policyIds: ['pol-h1', 'pol-nppf-11'],
    weight: 'decisive',
    direction: 'supports',
    settled: true
  },
  {
    id: 'con-supply-gap',
    issue: 'Housing Supply Gap',
    interpretationId: 'int-delivery-gap',
    policyIds: ['pol-s1', 'pol-h1'],
    weight: 'significant',
    direction: 'supports',
    settled: false
  },
  {
    id: 'con-retail-policy',
    issue: 'Retail Protection Policy',
    interpretationId: 'int-marketing',
    policyIds: ['pol-dm12', 'pol-nppf-86'],
    weight: 'significant',
    direction: 'neutral',
    settled: true,
    tensions: ['con-vitality']
  },
  {
    id: 'con-vitality',
    issue: 'Centre Vitality Impact',
    interpretationId: 'int-vitality',
    policyIds: ['pol-dm12'],
    weight: 'moderate',
    direction: 'supports',
    settled: false,
    tensions: ['con-retail-policy']
  }
];

// ============================================================================
// SCENARIOS & FRAMINGS
// ============================================================================

export interface PoliticalFraming {
  id: string;
  title: string;
  description: string;
  goals: string[];
  constraints: string[];
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  type: 'plan_option' | 'dm_position';
}

export interface ScenarioFramingTab {
  id: string;
  scenarioId: string;
  framingId: string;
  runId: string;
  position: string;
  confidence: 'high' | 'medium' | 'low';
  assumptions: string[];
  uncertainties: string[];
}

export const mockFramings: PoliticalFraming[] = [
  {
    id: 'high-growth',
    title: 'High Growth / Housing Delivery',
    description: 'Prioritise meeting housing needs quickly, maximise delivery, accept higher change where necessary.',
    goals: ['Maximise housing delivery', 'Prioritise accessibility and infrastructure unlocks'],
    constraints: ['Avoid unlawful allocations', 'Respect absolute constraints (Habitats Regulations)']
  },
  {
    id: 'heritage-balanced',
    title: 'Heritage / Landscape Protection',
    description: 'Prioritise protection of heritage assets and landscape character; accept lower growth if the alternative implies substantial harm.',
    goals: ['Avoid substantial harm to heritage significance', 'Direct growth to lower sensitivity locations'],
    constraints: ['Require strong evidence for any harm']
  },
  {
    id: 'climate-nature',
    title: 'Climate & Nature First',
    description: 'Prioritise carbon reduction, biodiversity net gain, flood resilience; treat growth as conditional on robust mitigation.',
    goals: ['Minimise emissions', 'Strengthen biodiversity and green infrastructure'],
    constraints: ['Avoid strategies relying on unproven mitigation']
  }
];

export const mockScenarios: Scenario[] = [
  {
    id: 'urban-intensification',
    name: 'Urban Intensification',
    description: 'Concentrate growth within existing urban area through brownfield development and gentle densification.',
    type: 'plan_option'
  },
  {
    id: 'edge-expansion',
    name: 'Edge Expansion',
    description: 'Extend urban area through strategic edge-of-city allocations on greenfield land.',
    type: 'plan_option'
  },
  {
    id: 'approve',
    name: 'Approve',
    description: 'Grant planning permission subject to conditions.',
    type: 'dm_position'
  },
  {
    id: 'refuse',
    name: 'Refuse',
    description: 'Refuse planning permission citing policy conflict.',
    type: 'dm_position'
  }
];

export const mockTabs: ScenarioFramingTab[] = [
  {
    id: 'tab-1',
    scenarioId: 'urban-intensification',
    framingId: 'high-growth',
    runId: 'run_8a4f2e',
    position: 'Urban intensification can deliver approximately 1,400 dpa, leaving a 400 dpa shortfall against target. Under a growth-focused framing, this shortfall is material and requires either supplementary allocations or a justified lower target.',
    confidence: 'medium',
    assumptions: ['Delivery rates match SHLAA projections', 'No major infrastructure constraints'],
    uncertainties: ['Viability on complex brownfield sites', 'Community acceptance of density']
  },
  {
    id: 'tab-2',
    scenarioId: 'urban-intensification',
    framingId: 'heritage-balanced',
    runId: 'run_8a4f2e',
    position: 'Urban intensification must respect conservation area character and historic skyline. Under heritage-balanced framing, reduced capacity in sensitive areas (~200 units) is acceptable to protect significance.',
    confidence: 'medium',
    assumptions: ['Design quality can be secured through policy', 'Height limits enforceable'],
    uncertainties: ['Appeal decisions on density in conservation areas']
  },
  {
    id: 'tab-3',
    scenarioId: 'edge-expansion',
    framingId: 'high-growth',
    runId: 'run_7b3c1d',
    position: 'Edge expansion can deliver full housing target plus contingency (~2,200 dpa). Green Belt harm is substantial but can be justified by exceptional circumstances under growth-focused framing.',
    confidence: 'high',
    assumptions: ['Strategic infrastructure is fundable', 'DfT road funding confirmed'],
    uncertainties: ['DfT funding timelines', 'Developer contributions viability']
  }
];

// ============================================================================
// TRACE & PROVENANCE
// ============================================================================

export type ReasoningMove = 
  | 'framing' 
  | 'issues' 
  | 'evidence' 
  | 'interpretation' 
  | 'considerations' 
  | 'balance' 
  | 'negotiation' 
  | 'positioning';

export interface MoveEvent {
  id: string;
  runId: string;
  move: ReasoningMove;
  status: 'complete' | 'in-progress' | 'pending';
  timestamp: string;
  inputIds: string[];
  outputIds: string[];
}

export interface ToolRun {
  id: string;
  runId: string;
  tool: string;
  model?: string;
  promptVersion?: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  limitations?: string;
  timestamp: string;
  durationMs: number;
}

export interface AuditEvent {
  id: string;
  runId: string;
  userId: string;
  action: 'tab_selected' | 'suggestion_accepted' | 'suggestion_rejected' | 'consideration_added' | 'sign_off';
  targetId: string;
  timestamp: string;
  note?: string;
}

export const mockMoveEvents: MoveEvent[] = [
  {
    id: 'move-1',
    runId: 'run_8a4f2e',
    move: 'framing',
    status: 'complete',
    timestamp: '2024-12-18T09:00:00Z',
    inputIds: ['high-growth'],
    outputIds: ['framing-obj-1']
  },
  {
    id: 'move-2',
    runId: 'run_8a4f2e',
    move: 'issues',
    status: 'complete',
    timestamp: '2024-12-18T09:02:00Z',
    inputIds: ['framing-obj-1'],
    outputIds: ['issue-housing', 'issue-transport', 'issue-heritage']
  },
  {
    id: 'move-3',
    runId: 'run_8a4f2e',
    move: 'evidence',
    status: 'complete',
    timestamp: '2024-12-18T09:05:00Z',
    inputIds: ['issue-housing', 'issue-transport'],
    outputIds: ['ev-census-2021', 'ev-affordability', 'ev-transport-dft']
  },
  {
    id: 'move-4',
    runId: 'run_8a4f2e',
    move: 'interpretation',
    status: 'complete',
    timestamp: '2024-12-18T09:10:00Z',
    inputIds: ['ev-census-2021', 'ev-affordability'],
    outputIds: ['int-housing-need', 'int-delivery-gap']
  },
  {
    id: 'move-5',
    runId: 'run_8a4f2e',
    move: 'considerations',
    status: 'complete',
    timestamp: '2024-12-18T09:15:00Z',
    inputIds: ['int-housing-need', 'pol-h1'],
    outputIds: ['con-housing-need', 'con-supply-gap']
  },
  {
    id: 'move-6',
    runId: 'run_8a4f2e',
    move: 'balance',
    status: 'in-progress',
    timestamp: '2024-12-18T09:20:00Z',
    inputIds: ['con-housing-need', 'con-supply-gap'],
    outputIds: []
  },
  {
    id: 'move-7',
    runId: 'run_8a4f2e',
    move: 'negotiation',
    status: 'pending',
    timestamp: '',
    inputIds: [],
    outputIds: []
  },
  {
    id: 'move-8',
    runId: 'run_8a4f2e',
    move: 'positioning',
    status: 'pending',
    timestamp: '',
    inputIds: [],
    outputIds: []
  }
];

export const mockToolRuns: ToolRun[] = [
  {
    id: 'tool-1',
    runId: 'run_8a4f2e',
    tool: 'policy_retrieval',
    model: 'text-embedding-3-small',
    inputs: { query: 'housing delivery Cambridge local plan', top_k: 10 },
    outputs: { results: ['pol-h1', 'pol-s1', 'pol-nppf-11'] },
    timestamp: '2024-12-18T09:03:00Z',
    durationMs: 450
  },
  {
    id: 'tool-2',
    runId: 'run_8a4f2e',
    tool: 'evidence_synthesis',
    model: 'claude-sonnet-4-20250514',
    promptVersion: 'v2.3.1',
    inputs: { evidence_ids: ['ev-census-2021', 'ev-affordability'], question: 'What is the housing need situation?' },
    outputs: { interpretation: 'int-housing-need' },
    limitations: 'Cannot independently verify primary data sources.',
    timestamp: '2024-12-18T09:08:00Z',
    durationMs: 2340
  },
  {
    id: 'tool-3',
    runId: 'run_8a4f2e',
    tool: 'dft_connectivity',
    inputs: { location: 'Cambridge', modes: ['rail', 'bus', 'cycle'] },
    outputs: { metrics: { rail_london: 50, bus_coverage: 0.78, cycle_km: 142 } },
    limitations: 'Does not model capacity constraints or congestion.',
    timestamp: '2024-12-18T09:06:00Z',
    durationMs: 1200
  }
];

export const mockAuditEvents: AuditEvent[] = [
  {
    id: 'audit-1',
    runId: 'run_8a4f2e',
    userId: 'sarah.mitchell',
    action: 'tab_selected',
    targetId: 'tab-1',
    timestamp: '2024-12-18T10:00:00Z'
  },
  {
    id: 'audit-2',
    runId: 'run_8a4f2e',
    userId: 'sarah.mitchell',
    action: 'suggestion_accepted',
    targetId: 'int-housing-need',
    timestamp: '2024-12-18T10:05:00Z',
    note: 'Interpretation aligns with member briefing.'
  },
  {
    id: 'audit-3',
    runId: 'run_8a4f2e',
    userId: 'sarah.mitchell',
    action: 'consideration_added',
    targetId: 'con-housing-need',
    timestamp: '2024-12-18T10:10:00Z'
  }
];

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

export function getEvidenceById(id: string): EvidenceCard | undefined {
  return mockEvidenceCards.find(e => e.id === id);
}

export function getPolicyById(id: string): PolicyChip | undefined {
  return mockPolicies.find(p => p.id === id);
}

export function getConsiderationsByIssue(issue: string): Consideration[] {
  return mockConsiderations.filter(c => c.issue.toLowerCase().includes(issue.toLowerCase()));
}

export function getMoveStatus(runId: string): Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'> {
  const moves = mockMoveEvents.filter(m => m.runId === runId);
  const result: Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'> = {
    framing: 'pending',
    issues: 'pending',
    evidence: 'pending',
    interpretation: 'pending',
    considerations: 'pending',
    balance: 'pending',
    negotiation: 'pending',
    positioning: 'pending'
  };
  
  for (const move of moves) {
    result[move.move] = move.status;
  }
  
  return result;
}

export function getTraceForElement(elementId: string): { moves: MoveEvent[]; tools: ToolRun[]; audit: AuditEvent[] } {
  // Simplified trace lookup - in real system would traverse graph
  const relatedMoves = mockMoveEvents.filter(m => 
    m.inputIds.includes(elementId) || m.outputIds.includes(elementId)
  );
  const relatedTools = mockToolRuns.filter(t => 
    Object.values(t.inputs).flat().includes(elementId) ||
    Object.values(t.outputs).flat().includes(elementId)
  );
  const relatedAudit = mockAuditEvents.filter(a => a.targetId === elementId);
  
  return { moves: relatedMoves, tools: relatedTools, audit: relatedAudit };
}
