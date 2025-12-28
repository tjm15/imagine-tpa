/**
 * Extended Mock Data for Full Interactive Demo
 * 
 * Includes:
 * - CULP stage configurations with deliverables and AI prompts
 * - GeoJSON for MapLibre layers
 * - Photos and additional fixtures
 * - AI response templates
 */

import { 
  CulpStage, 
  EvidenceCard, 
  PolicyChip, 
  Consideration,
  ReasoningMove 
} from './mockData';

// ============================================================================
// CULP STAGE CONFIGURATIONS
// ============================================================================

export interface CulpStageConfig {
  id: string;
  name: string;
  phase: 'getting-ready' | 'preparation' | 'submission' | 'adoption' | 'monitoring';
  description: string;
  status: 'complete' | 'in-progress' | 'blocked' | 'not-started';
  dueDate: string;
  deliverables: StageDeliverable[];
  aiPrompts: AIPromptConfig[];
  warnings: StageWarning[];
  checklist: ChecklistItem[];
}

export interface StageDeliverable {
  id: string;
  name: string;
  type: 'document' | 'map' | 'dataset' | 'bundle';
  status: 'complete' | 'draft' | 'not-started';
  dueDate: string;
  template?: string;
}

export interface AIPromptConfig {
  id: string;
  label: string;
  description: string;
  category: 'draft' | 'review' | 'check' | 'suggest';
}

export interface StageWarning {
  id: string;
  severity: 'critical' | 'major' | 'minor';
  message: string;
  actionLabel?: string;
}

export interface ChecklistItem {
  id: string;
  label: string;
  checked: boolean;
  required: boolean;
}

export const culpStageConfigs: CulpStageConfig[] = [
  {
    id: 'sea-screening',
    name: 'SEA Screening',
    phase: 'getting-ready',
    description: 'Determine whether Strategic Environmental Assessment is required',
    status: 'complete',
    dueDate: '2024-10-15',
    deliverables: [
      { id: 'sea-record', name: 'SEA Requirement Record', type: 'document', status: 'complete', dueDate: '2024-10-15' },
    ],
    aiPrompts: [
      { id: 'sea-draft', label: 'Draft SEA screening', description: 'Generate SEA screening determination', category: 'draft' },
    ],
    warnings: [],
    checklist: [
      { id: 'sea-1', label: 'Consulted statutory bodies', checked: true, required: true },
      { id: 'sea-2', label: 'Published screening decision', checked: true, required: true },
    ],
  },
  {
    id: 'timetable',
    name: 'Timetable',
    phase: 'getting-ready',
    description: 'Publish Local Development Scheme with 30-month timetable',
    status: 'complete',
    dueDate: '2024-11-01',
    deliverables: [
      { id: 'lds', name: 'Local Development Scheme', type: 'document', status: 'complete', dueDate: '2024-11-01' },
      { id: 'milestones', name: 'Milestones Table', type: 'dataset', status: 'complete', dueDate: '2024-11-01' },
    ],
    aiPrompts: [],
    warnings: [],
    checklist: [
      { id: 'tt-1', label: 'Council approval obtained', checked: true, required: true },
      { id: 'tt-2', label: 'LDS published online', checked: true, required: true },
    ],
  },
  {
    id: 'notice',
    name: 'Notice of Plan-Making',
    phase: 'getting-ready',
    description: 'Formal public notice of intention to prepare local plan',
    status: 'complete',
    dueDate: '2024-11-15',
    deliverables: [
      { id: 'notice-html', name: 'Public Notice', type: 'document', status: 'complete', dueDate: '2024-11-15' },
      { id: 'boundary-map', name: 'Plan Boundary Map', type: 'map', status: 'complete', dueDate: '2024-11-15' },
    ],
    aiPrompts: [],
    warnings: [],
    checklist: [
      { id: 'not-1', label: 'Notice published', checked: true, required: true },
      { id: 'not-2', label: 'Boundary geometry uploaded', checked: true, required: true },
    ],
  },
  {
    id: 'scoping',
    name: 'Scoping Consultation',
    phase: 'getting-ready',
    description: 'Early engagement on plan scope and key issues',
    status: 'complete',
    dueDate: '2024-12-15',
    deliverables: [
      { id: 'scoping-doc', name: 'Scoping Document', type: 'document', status: 'complete', dueDate: '2024-12-01' },
      { id: 'consultee-list', name: 'Consultee List', type: 'dataset', status: 'complete', dueDate: '2024-12-01' },
      { id: 'responses-log', name: 'Responses Log', type: 'dataset', status: 'complete', dueDate: '2024-12-15' },
    ],
    aiPrompts: [
      { id: 'scope-summary', label: 'Summarise responses', description: 'AI summary of consultation responses by theme', category: 'review' },
    ],
    warnings: [],
    checklist: [
      { id: 'sc-1', label: 'Statutory consultees notified', checked: true, required: true },
      { id: 'sc-2', label: 'Minimum 6 weeks consultation', checked: true, required: true },
      { id: 'sc-3', label: 'Responses logged and themed', checked: true, required: true },
    ],
  },
  {
    id: 'baseline',
    name: 'Baseline & Place Portrait',
    phase: 'getting-ready',
    description: 'Establish evidence base and characterise the place',
    status: 'in-progress',
    dueDate: '2025-03-31',
    deliverables: [
      { id: 'place-portrait', name: 'Place Portrait', type: 'document', status: 'draft', dueDate: '2025-02-28' },
      { id: 'evidence-index', name: 'Evidence Base Index', type: 'dataset', status: 'draft', dueDate: '2025-03-15' },
      { id: 'housing-baseline', name: 'Housing Baseline', type: 'document', status: 'complete', dueDate: '2025-01-31' },
      { id: 'transport-baseline', name: 'Transport Baseline', type: 'document', status: 'not-started', dueDate: '2025-02-28' },
      { id: 'environment-baseline', name: 'Environment Baseline', type: 'document', status: 'draft', dueDate: '2025-02-28' },
    ],
    aiPrompts: [
      { id: 'baseline-draft', label: 'Draft baseline section', description: 'Generate baseline narrative from evidence', category: 'draft' },
      { id: 'baseline-gaps', label: 'Identify evidence gaps', description: 'Scan for missing evidence', category: 'check' },
      { id: 'baseline-compare', label: 'Compare with neighbours', description: 'Benchmark against similar authorities', category: 'suggest' },
    ],
    warnings: [
      { id: 'warn-transport', severity: 'major', message: 'Transport baseline incomplete - awaiting DfT data refresh', actionLabel: 'Chase DfT' },
      { id: 'warn-heritage', severity: 'minor', message: 'Conservation area appraisals last updated 2018', actionLabel: 'Schedule update' },
    ],
    checklist: [
      { id: 'bl-1', label: 'Housing need evidence (SHMA)', checked: true, required: true },
      { id: 'bl-2', label: 'Employment land review', checked: true, required: true },
      { id: 'bl-3', label: 'Transport baseline', checked: false, required: true },
      { id: 'bl-4', label: 'Environmental constraints mapping', checked: true, required: true },
      { id: 'bl-5', label: 'Heritage assets register', checked: true, required: false },
      { id: 'bl-6', label: 'Retail/town centre study', checked: false, required: false },
    ],
  },
  {
    id: 'gateway-1',
    name: 'Gateway 1',
    phase: 'getting-ready',
    description: 'Readiness check before starting 30-month clock',
    status: 'not-started',
    dueDate: '2025-04-30',
    deliverables: [
      { id: 'self-assessment-1', name: 'Self-Assessment Summary', type: 'document', status: 'not-started', dueDate: '2025-04-15' },
      { id: 'readiness-output', name: 'Readiness Checker Output', type: 'document', status: 'not-started', dueDate: '2025-04-20' },
    ],
    aiPrompts: [
      { id: 'g1-check', label: 'Run readiness check', description: 'Simulate Planning Inspectorate gateway assessment', category: 'check' },
      { id: 'g1-remediate', label: 'Generate remediation plan', description: 'Action plan for identified gaps', category: 'suggest' },
    ],
    warnings: [],
    checklist: [
      { id: 'g1-1', label: 'Evidence base substantially complete', checked: false, required: true },
      { id: 'g1-2', label: 'Scoping consultation complete', checked: true, required: true },
      { id: 'g1-3', label: 'Timetable confirmed', checked: true, required: true },
      { id: 'g1-4', label: 'Resources secured', checked: false, required: true },
    ],
  },
  {
    id: 'vision',
    name: 'Vision & Outcomes',
    phase: 'preparation',
    description: 'Establish plan vision and up to 10 measurable outcomes',
    status: 'not-started',
    dueDate: '2025-06-30',
    deliverables: [
      { id: 'vision-statement', name: 'Vision Statement', type: 'document', status: 'not-started', dueDate: '2025-05-31' },
      { id: 'outcomes-list', name: 'Outcomes List (max 10)', type: 'document', status: 'not-started', dueDate: '2025-06-15' },
    ],
    aiPrompts: [
      { id: 'vision-draft', label: 'Draft vision statement', description: 'Generate vision based on place portrait', category: 'draft' },
      { id: 'outcomes-suggest', label: 'Suggest outcomes', description: 'Propose measurable outcomes aligned to vision', category: 'suggest' },
      { id: 'outcomes-check', label: 'Check coherence', description: 'Identify conflicts between outcomes', category: 'check' },
    ],
    warnings: [],
    checklist: [
      { id: 'vis-1', label: 'Member engagement on vision', checked: false, required: true },
      { id: 'vis-2', label: 'Outcomes are measurable', checked: false, required: true },
      { id: 'vis-3', label: 'Maximum 10 outcomes', checked: false, required: true },
    ],
  },
  {
    id: 'sites-options',
    name: 'Options & Sites',
    phase: 'preparation',
    description: 'Develop spatial options and assess site allocations',
    status: 'not-started',
    dueDate: '2025-12-31',
    deliverables: [
      { id: 'shlaa-update', name: 'SHLAA Update', type: 'dataset', status: 'not-started', dueDate: '2025-08-31' },
      { id: 'site-assessments', name: 'Site Assessments', type: 'bundle', status: 'not-started', dueDate: '2025-10-31' },
      { id: 'spatial-options', name: 'Spatial Options Report', type: 'document', status: 'not-started', dueDate: '2025-11-30' },
      { id: 'alternatives-log', name: 'Reasonable Alternatives Log', type: 'dataset', status: 'not-started', dueDate: '2025-12-15' },
    ],
    aiPrompts: [
      { id: 'site-assess', label: 'Assess site suitability', description: 'Generate site assessment from constraints', category: 'draft' },
      { id: 'site-compare', label: 'Compare allocations', description: 'Tabular comparison of candidate sites', category: 'review' },
      { id: 'options-generate', label: 'Generate spatial options', description: 'Propose alternative strategies', category: 'suggest' },
    ],
    warnings: [],
    checklist: [
      { id: 'so-1', label: 'Call for sites complete', checked: false, required: true },
      { id: 'so-2', label: 'Constraint screening complete', checked: false, required: true },
      { id: 'so-3', label: 'Minimum 3 reasonable alternatives', checked: false, required: true },
      { id: 'so-4', label: 'SA/SEA of alternatives', checked: false, required: true },
    ],
  },
];

// ============================================================================
// GEOJSON DATA FOR MAPLIBRE
// ============================================================================

export const cambridgeBoundary: GeoJSON.Feature<GeoJSON.Polygon> = {
  type: 'Feature',
  properties: {
    name: 'Cambridge City Council',
    gss_code: 'E07000008',
  },
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [0.0576, 52.1739],
      [0.0604, 52.1857],
      [0.0789, 52.1963],
      [0.1012, 52.2076],
      [0.1245, 52.2134],
      [0.1456, 52.2189],
      [0.1634, 52.2156],
      [0.1789, 52.2089],
      [0.1912, 52.1978],
      [0.1934, 52.1823],
      [0.1856, 52.1689],
      [0.1723, 52.1567],
      [0.1534, 52.1489],
      [0.1289, 52.1456],
      [0.1056, 52.1478],
      [0.0823, 52.1534],
      [0.0634, 52.1623],
      [0.0576, 52.1739],
    ]],
  },
};

// ============================================================================
// SAAD INDICATOR TYPES (Suitability, Availability, Achievability, Deliverability)
// ============================================================================

export type SAADStatus = 'green' | 'amber' | 'red';

export interface SAADIndicators {
  suitability: SAADStatus;
  availability: SAADStatus;
  achievability: SAADStatus;
  deliverability: SAADStatus;
}

export interface SiteConstraint {
  id: string;
  name: string;
  severity: 'high' | 'medium' | 'low';
  implications: string;
  mitigation: string;
}

export interface EnrichedSiteProperties {
  id: string;
  name: string;
  capacity: number;
  status: 'shortlisted' | 'under-assessment' | 'committed' | 'omitted';
  landType: 'brownfield' | 'greenfield' | 'urban-extension';
  greenBelt: boolean;
  aiSummary: string;
  saad: SAADIndicators;
  accessibilityScore: number; // 0-10
  sustainabilityScore: number; // 0-10
  constraints: SiteConstraint[];
}

export const siteAllocations: GeoJSON.FeatureCollection<GeoJSON.Polygon, EnrichedSiteProperties> = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: {
        id: 'SHLAA/045',
        name: 'Northern Fringe',
        capacity: 450,
        status: 'shortlisted',
        landType: 'greenfield',
        greenBelt: true,
        aiSummary: 'Large greenfield site adjacent to Cambridge Science Park offering strategic capacity for employment-led mixed-use development. Green Belt release would require exceptional circumstances justification.',
        saad: { suitability: 'amber', availability: 'green', achievability: 'amber', deliverability: 'green' },
        accessibilityScore: 7.2,
        sustainabilityScore: 6.8,
        constraints: [
          { id: 'c1', name: 'Contaminated Land', severity: 'medium', implications: 'Former industrial use requires Phase 2 investigation. May affect viability.', mitigation: 'Remediation strategy to be secured via condition. Cost estimate £1.2m included in viability.' },
          { id: 'c2', name: 'Noise (A14)', severity: 'low', implications: 'Northern boundary within 55dB contour from A14.', mitigation: 'Acoustic buffer zone and building orientation. No residential within 50m of boundary.' },
          { id: 'c3', name: 'Green Belt', severity: 'high', implications: 'Site is within Cambridge Green Belt. Release requires exceptional circumstances.', mitigation: 'Compensatory improvements to remaining Green Belt. Strong sustainability case for employment-led growth.' },
        ],
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [0.1256, 52.2134],
          [0.1312, 52.2145],
          [0.1334, 52.2112],
          [0.1289, 52.2098],
          [0.1256, 52.2134],
        ]],
      },
    },
    {
      type: 'Feature',
      properties: {
        id: 'SHLAA/067',
        name: 'Southern Gateway',
        capacity: 320,
        status: 'under-assessment',
        landType: 'brownfield',
        greenBelt: false,
        aiSummary: 'Previously developed industrial land with excellent public transport links via Cambridge South station. Flood risk requires sequential approach but site passes the exception test.',
        saad: { suitability: 'green', availability: 'amber', achievability: 'green', deliverability: 'amber' },
        accessibilityScore: 8.8,
        sustainabilityScore: 9.1,
        constraints: [
          { id: 'c4', name: 'Flood Zone 2', severity: 'medium', implications: 'Eastern portion in Flood Zone 2. Sequential test required.', mitigation: 'Site layout places vulnerable uses in Zone 1. SUDS and finished floor levels +600mm above 1:100+CC.' },
        ],
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [0.1189, 52.1534],
          [0.1245, 52.1556],
          [0.1278, 52.1523],
          [0.1223, 52.1501],
          [0.1189, 52.1534],
        ]],
      },
    },
    {
      type: 'Feature',
      properties: {
        id: 'SHLAA/089',
        name: 'Eastern Expansion',
        capacity: 680,
        status: 'shortlisted',
        landType: 'urban-extension',
        greenBelt: true,
        aiSummary: 'Strategic urban extension providing the largest single site capacity. Infrastructure requirements are significant but deliverable within plan period with phased approach.',
        saad: { suitability: 'green', availability: 'green', achievability: 'amber', deliverability: 'amber' },
        accessibilityScore: 6.5,
        sustainabilityScore: 7.4,
        constraints: [
          { id: 'c5', name: 'Heritage Proximity', severity: 'medium', implications: 'Site adjoins Leper Chapel (Grade I). Setting assessment required.', mitigation: 'Landscaped buffer and sensitive design. Historic England engaged in masterplanning.' },
          { id: 'c6', name: 'Green Belt', severity: 'high', implications: 'Major Green Belt release. Strategic importance requires robust justification.', mitigation: 'Comprehensive Green Belt review demonstrates reduced contribution to GB purposes. New defensible boundary.' },
        ],
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [0.1756, 52.1823],
          [0.1834, 52.1856],
          [0.1889, 52.1801],
          [0.1812, 52.1767],
          [0.1756, 52.1823],
        ]],
      },
    },
    {
      type: 'Feature',
      properties: {
        id: 'BF/012',
        name: 'Station Area Regeneration',
        capacity: 280,
        status: 'committed',
        landType: 'brownfield',
        greenBelt: false,
        aiSummary: 'Committed brownfield regeneration with planning permission granted. Highly sustainable location at Cambridge Central station. Delivery on track for 2026 start.',
        saad: { suitability: 'green', availability: 'green', achievability: 'green', deliverability: 'green' },
        accessibilityScore: 9.5,
        sustainabilityScore: 9.3,
        constraints: [],
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [0.1334, 52.1923],
          [0.1378, 52.1945],
          [0.1401, 52.1912],
          [0.1356, 52.1889],
          [0.1334, 52.1923],
        ]],
      },
    },
    {
      type: 'Feature',
      properties: {
        id: 'SHLAA/102',
        name: 'West Cambridge Extension',
        capacity: 520,
        status: 'shortlisted',
        landType: 'greenfield',
        greenBelt: true,
        aiSummary: 'University-adjacent site offering research-led development opportunity. Strong functional relationship with West Cambridge campus but Green Belt sensitivity.',
        saad: { suitability: 'amber', availability: 'green', achievability: 'green', deliverability: 'green' },
        accessibilityScore: 7.8,
        sustainabilityScore: 7.1,
        constraints: [
          { id: 'c7', name: 'Green Belt', severity: 'high', implications: 'Green Belt site with high landscape sensitivity.', mitigation: 'Integrated with university campus. Landscape-led masterplan.' },
          { id: 'c8', name: 'Ecology', severity: 'medium', implications: 'Protected species (great crested newts) present.', mitigation: 'Receptor site identified. District Level Licensing in place.' },
        ],
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [0.0856, 52.2034],
          [0.0923, 52.2067],
          [0.0978, 52.2034],
          [0.0912, 52.2001],
          [0.0856, 52.2034],
        ]],
      },
    },
  ],
};

// ============================================================================
// STRATEGIC SCENARIOS
// ============================================================================

export interface StrategicScenario {
  id: string;
  name: string;
  description: string;
  allocatedSiteIds: string[];
  omittedSiteIds: string[];
  totalCapacity: number;
  narrative: string;
  color: 'blue' | 'amber' | 'emerald' | 'purple';
}

export const strategicScenarios: StrategicScenario[] = [
  {
    id: 'scenario-transit',
    name: 'Transit-Oriented Innovation',
    description: 'Prioritise brownfield sites with excellent public transport accessibility',
    allocatedSiteIds: ['SHLAA/067', 'BF/012', 'SHLAA/102'],
    omittedSiteIds: ['SHLAA/045', 'SHLAA/089'],
    totalCapacity: 1120,
    narrative: 'This scenario focuses growth on brownfield and previously developed land with strong public transport connections. The Southern Gateway and Station Area sites anchor the strategy, with West Cambridge providing research-led housing. Green Belt sites are excluded, limiting overall capacity but minimising landscape impact. This approach strongly aligns with climate objectives but may face deliverability challenges meeting the full housing target.',
    color: 'blue',
  },
  {
    id: 'scenario-heritage',
    name: 'Heritage-Led Infill',
    description: 'Maximise brownfield capacity while protecting heritage assets',
    allocatedSiteIds: ['SHLAA/067', 'BF/012'],
    omittedSiteIds: ['SHLAA/045', 'SHLAA/089', 'SHLAA/102'],
    totalCapacity: 600,
    narrative: 'A conservative strategy that allocates only sites with minimal heritage impact and no Green Belt release. This protects Cambridge\'s historic character but significantly undersupplies against housing need. Additional allocations would be required in the next plan period, likely requiring difficult decisions on currently omitted sites.',
    color: 'amber',
  },
  {
    id: 'scenario-strategic',
    name: 'Strategic Urban Extensions',
    description: 'Maximise capacity through strategic Green Belt releases',
    allocatedSiteIds: ['SHLAA/045', 'SHLAA/067', 'SHLAA/089', 'BF/012', 'SHLAA/102'],
    omittedSiteIds: [],
    totalCapacity: 2250,
    narrative: 'This scenario allocates all assessed sites to maximise housing delivery and support economic growth. It requires exceptional circumstances justification for Green Belt release but provides a comprehensive housing land supply with headroom. Infrastructure requirements are significant but achievable with developer contributions and public investment in transport improvements.',
    color: 'emerald',
  },
];

// Helper functions for scenarios
export function getScenarioById(id: string): StrategicScenario | undefined {
  return strategicScenarios.find(s => s.id === id);
}

export function getSitesForScenario(scenarioId: string): {
  allocated: GeoJSON.Feature<GeoJSON.Polygon, EnrichedSiteProperties>[];
  omitted: GeoJSON.Feature<GeoJSON.Polygon, EnrichedSiteProperties>[];
} {
  const scenario = getScenarioById(scenarioId);
  if (!scenario) return { allocated: [], omitted: [] };
  
  return {
    allocated: siteAllocations.features.filter(f => 
      scenario.allocatedSiteIds.includes(f.properties.id)
    ),
    omitted: siteAllocations.features.filter(f => 
      scenario.omittedSiteIds.includes(f.properties.id)
    ),
  };
}

export function getEnrichedSiteById(id: string): GeoJSON.Feature<GeoJSON.Polygon, EnrichedSiteProperties> | undefined {
  return siteAllocations.features.find(f => f.properties.id === id);
}

export const constraintsLayers: Record<string, GeoJSON.FeatureCollection> = {
  greenBelt: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { name: 'Cambridge Green Belt' },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [0.0456, 52.1623],
            [0.0534, 52.1956],
            [0.0823, 52.2189],
            [0.1089, 52.2234],
            [0.1123, 52.2156],
            [0.0934, 52.1934],
            [0.0723, 52.1756],
            [0.0567, 52.1634],
            [0.0456, 52.1623],
          ]],
        },
      },
    ],
  },
  floodZone: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { name: 'Flood Zone 2', risk: 'medium' },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [0.1156, 52.1489],
            [0.1289, 52.1589],
            [0.1312, 52.1534],
            [0.1178, 52.1456],
            [0.1156, 52.1489],
          ]],
        },
      },
    ],
  },
  conservationAreas: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { name: 'Historic Core Conservation Area', designated: '1969' },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [0.1156, 52.2012],
            [0.1223, 52.2045],
            [0.1289, 52.2023],
            [0.1256, 52.1978],
            [0.1189, 52.1989],
            [0.1156, 52.2012],
          ]],
        },
      },
      {
        type: 'Feature',
        properties: { name: 'Mill Road Conservation Area', designated: '1993' },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [0.1334, 52.1934],
            [0.1389, 52.1956],
            [0.1423, 52.1923],
            [0.1367, 52.1901],
            [0.1334, 52.1934],
          ]],
        },
      },
    ],
  },
};

// ============================================================================
// PHOTOS FOR LIGHTBOX
// ============================================================================

export interface SitePhoto {
  id: string;
  siteId: string;
  url: string;
  caption: string;
  date: string;
  type: 'aerial' | 'street' | 'context' | 'detail';
  metadata?: {
    bearing?: number;
    lat?: number;
    lon?: number;
  };
}

const demoPhotoUrl = (fileName: string) => new URL(`../assets/demo/${fileName}`, import.meta.url).toString();

export const mockPhotos: SitePhoto[] = [
  {
    id: 'photo-1',
    siteId: 'SHLAA/045',
    url: demoPhotoUrl('northern-fringe-street.svg'),
    caption: 'Northern Fringe site - view from Milton Road looking north',
    date: '2024-12-10',
    type: 'street',
    metadata: { bearing: 0, lat: 52.2134, lon: 0.1278 },
  },
  {
    id: 'photo-2',
    siteId: 'SHLAA/045',
    url: demoPhotoUrl('northern-fringe-aerial.svg'),
    caption: 'Northern Fringe - aerial context showing Science Park adjacency',
    date: '2024-11-15',
    type: 'aerial',
  },
  {
    id: 'photo-3',
    siteId: 'SHLAA/067',
    url: demoPhotoUrl('southern-gateway-context.svg'),
    caption: 'Southern Gateway - existing industrial buildings',
    date: '2024-12-08',
    type: 'context',
  },
  {
    id: 'photo-4',
    siteId: 'site-mill-road',
    url: demoPhotoUrl('mill-road-frontage.svg'),
    caption: '45 Mill Road - street frontage',
    date: '2024-12-12',
    type: 'street',
  },
  {
    id: 'photo-5',
    siteId: 'site-mill-road',
    url: demoPhotoUrl('mill-road-courtyard.svg'),
    caption: '45 Mill Road - rear courtyard access',
    date: '2024-12-12',
    type: 'detail',
  },
];

// Add helper properties for photo lightbox
export const mockPhotosForLightbox = mockPhotos.map(p => ({
  ...p,
  thumbnailUrl: p.url,
  fullUrl: p.url,
}));

// ============================================================================
// MOCK EVIDENCE FOR CONTEXT MARGIN
// ============================================================================

export interface Evidence {
  id: string;
  title: string;
  summary?: string;
  type: 'document' | 'policy' | 'map' | 'consultation' | 'photo';
  source?: string;
  date?: string;
  weight?: number;
}

export const mockEvidence: Evidence[] = [
  {
    id: 'ev-1',
    title: 'SHLAA 2024 Assessment',
    summary: 'Strategic Housing Land Availability Assessment identifying 45 candidate sites with combined capacity of 12,500 dwellings.',
    type: 'document',
    source: 'Cambridge City Council',
    date: '2024-09-15',
    weight: 0.9,
  },
  {
    id: 'ev-2',
    title: 'Green Belt Review',
    summary: 'Independent review of Green Belt boundaries identifying areas that no longer meet NPPF purposes.',
    type: 'document',
    source: 'Arup Consultants',
    date: '2024-06-30',
    weight: 0.85,
  },
  {
    id: 'ev-3',
    title: 'Policy GB1 - Green Belt',
    summary: 'Emerging policy restricting development within the Cambridge Green Belt except in very special circumstances.',
    type: 'policy',
    source: 'Draft Local Plan',
    date: '2024-11-01',
    weight: 0.95,
  },
  {
    id: 'ev-4',
    title: 'Transport Assessment',
    summary: 'County Council assessment of highway capacity constraints on northern radial routes.',
    type: 'document',
    source: 'Cambridgeshire CC Highways',
    date: '2024-08-20',
    weight: 0.75,
  },
  {
    id: 'ev-5',
    title: 'Flood Risk Map - Zone 2/3',
    summary: 'Environment Agency flood mapping showing Zone 2 and 3 extents updated December 2024.',
    type: 'map',
    source: 'Environment Agency',
    date: '2024-12-01',
    weight: 0.8,
  },
  {
    id: 'ev-6',
    title: 'Historic England Response',
    summary: 'Statutory consultee response highlighting heritage concerns for two proposed allocation sites.',
    type: 'consultation',
    source: 'Historic England',
    date: '2024-11-15',
    weight: 0.7,
  },
  {
    id: 'ev-7',
    title: 'Housing Needs Assessment',
    summary: 'Strategic Housing Market Assessment identifying need for 1,200 affordable homes per year.',
    type: 'document',
    source: 'GL Hearn',
    date: '2024-04-01',
    weight: 0.9,
  },
  {
    id: 'ev-8',
    title: 'Sustainability Appraisal',
    summary: 'SA of spatial options scoring all reasonable alternatives against 15 sustainability objectives.',
    type: 'document',
    source: 'LUC Consultants',
    date: '2024-10-15',
    weight: 0.85,
  },
];

// ============================================================================
// ADDITIONAL POLICY DETAILS
// ============================================================================

export interface PolicyDetail extends PolicyChip {
  fullText: string;
  adoptedDate: string;
  status: 'adopted' | 'emerging' | 'superseded';
  caseReferences?: string[];
  relatedPolicies: string[];
}

export const mockPolicyDetails: PolicyDetail[] = [
  {
    id: 'pol-dm12',
    reference: 'LP/2024/DM12',
    title: 'District Centre Vitality',
    source: 'local_plan',
    relevance: 'high',
    excerpt: 'Ground floor retail uses in District Centres will be protected unless marketing evidence demonstrates no demand over 12 months.',
    fullText: `Policy DM12: District Centre Vitality and Viability

1. Development proposals within designated District Centres should:
   a) Maintain and enhance the retail function of the centre;
   b) Provide active frontages at ground floor level;
   c) Support the vitality and viability of the centre as a whole.

2. The change of use of ground floor retail units (Use Class E(a)) to other uses will only be permitted where:
   a) The unit has been actively marketed for retail use for a continuous period of at least 12 months at a realistic market rent; and
   b) No reasonable offers have been received; and
   c) The proposed use would not harm the character or function of the centre.

3. Evidence of marketing must include:
   - Details of the marketing agent and their instructions;
   - Asking rent and any variations during the marketing period;
   - Details of enquiries received and reasons for rejection;
   - Evidence of advertisement in appropriate publications.

Reasoned Justification:
District Centres provide essential services to local communities and reduce the need to travel. This policy seeks to protect their retail function while recognising that some flexibility may be needed where retail use is demonstrably unviable.`,
    adoptedDate: '2024-06-15',
    status: 'adopted',
    caseReferences: ['APP/Q0505/W/23/3314567', 'APP/Q0505/W/22/3298123'],
    relatedPolicies: ['pol-s1', 'pol-nppf-86'],
  },
];

// ============================================================================
// CONSULTEE RESPONSES
// ============================================================================

export interface ConsulteeResponse {
  id: string;
  consultee: string;
  type: 'statutory' | 'public' | 'internal';
  receivedDate: string;
  status: 'no-objection' | 'objection' | 'holding' | 'support';
  summary: string;
  fullResponse: string;
  conditions?: string[];
}

export const mockConsulteeResponses: ConsulteeResponse[] = [
  {
    id: 'cons-1',
    consultee: 'Highway Authority',
    type: 'statutory',
    receivedDate: '2024-11-29',
    status: 'no-objection',
    summary: 'No objection subject to cycle storage condition',
    fullResponse: 'The Highway Authority has assessed this application and considers that the proposal would not have an unacceptable impact on highway safety or the residual cumulative impacts on the road network would not be severe. We therefore raise no objection subject to the following condition:\n\n- Prior to occupation, secure covered cycle storage for a minimum of 2 bicycles shall be provided in accordance with details to be submitted to and approved by the Local Planning Authority.',
    conditions: ['Cycle storage (2 spaces)'],
  },
  {
    id: 'cons-2',
    consultee: 'Conservation Officer',
    type: 'internal',
    receivedDate: '2024-12-02',
    status: 'no-objection',
    summary: 'Satisfied with internal conversion approach',
    fullResponse: 'The property is located within the Mill Road Conservation Area. The application proposes internal alterations only with no external changes. On this basis, I am satisfied that the proposal would preserve the character and appearance of the Conservation Area. No objection.',
    conditions: [],
  },
  {
    id: 'cons-3',
    consultee: 'Environment Agency',
    type: 'statutory',
    receivedDate: '2024-11-25',
    status: 'no-objection',
    summary: 'Site outside flood zones - no comments',
    fullResponse: 'The site is located in Flood Zone 1 and is therefore at low risk of flooding. We have no comments to make on this application.',
    conditions: [],
  },
];

// ============================================================================
// NOTIFICATION TEMPLATES
// ============================================================================

export interface NotificationTemplate {
  id: string;
  type: 'info' | 'warning' | 'error' | 'success' | 'ai';
  title: string;
  message: string;
  trigger: string;
}

export const notificationTemplates: NotificationTemplate[] = [
  {
    id: 'notif-evidence-cited',
    type: 'success',
    title: 'Evidence cited',
    message: 'Added citation to document',
    trigger: 'citation-added',
  },
  {
    id: 'notif-ai-complete',
    type: 'ai',
    title: 'AI generation complete',
    message: 'Draft content ready for review',
    trigger: 'ai-complete',
  },
  {
    id: 'notif-gateway-warning',
    type: 'warning',
    title: 'Gateway readiness issue',
    message: 'Evidence gap detected - transport baseline incomplete',
    trigger: 'gateway-check',
  },
  {
    id: 'notif-deadline',
    type: 'warning',
    title: 'Deadline approaching',
    message: 'Place Portrait due in 14 days',
    trigger: 'deadline-14d',
  },
];

// ============================================================================
// REVISION HISTORY
// ============================================================================

export interface Revision {
  id: string;
  documentId: string;
  version: string;
  author: string;
  timestamp: string;
  summary: string;
  changes: { section: string; type: 'added' | 'modified' | 'deleted'; preview: string }[];
}

export const mockRevisions: Revision[] = [
  {
    id: 'rev-1',
    documentId: 'place-portrait',
    version: '2.3',
    author: 'Sarah Mitchell',
    timestamp: '2024-12-18T14:30:00Z',
    summary: 'Updated housing affordability figures with Q3 2024 data',
    changes: [
      { section: 'Housing Context', type: 'modified', preview: 'Affordability ratio updated from 12.4x to 12.8x' },
      { section: 'Key Indicators', type: 'modified', preview: 'Added Q3 2024 source reference' },
    ],
  },
  {
    id: 'rev-2',
    documentId: 'place-portrait',
    version: '2.2',
    author: 'James Chen',
    timestamp: '2024-12-15T11:00:00Z',
    summary: 'Added transport connectivity section',
    changes: [
      { section: 'Transport & Connectivity', type: 'added', preview: 'New section covering rail, bus, cycling infrastructure' },
    ],
  },
  {
    id: 'rev-3',
    documentId: 'place-portrait',
    version: '2.1',
    author: 'Sarah Mitchell',
    timestamp: '2024-12-10T16:45:00Z',
    summary: 'Incorporated AI suggestions on knowledge economy context',
    changes: [
      { section: 'Economic Context', type: 'modified', preview: 'Added employment growth analysis' },
      { section: 'Housing Context', type: 'modified', preview: 'Linked housing pressure to jobs growth' },
    ],
  },
];

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

export function getStageById(id: string): CulpStageConfig | undefined {
  return culpStageConfigs.find(s => s.id === id);
}

export function getStageDeliverables(stageId: string): StageDeliverable[] {
  return getStageById(stageId)?.deliverables || [];
}

export function getStageWarnings(stageId: string): StageWarning[] {
  return getStageById(stageId)?.warnings || [];
}

export function getSiteAllocation(id: string): GeoJSON.Feature | undefined {
  return siteAllocations.features.find(f => f.properties?.id === id);
}

export function getPhotosBySite(siteId: string): SitePhoto[] {
  return mockPhotos.filter(p => p.siteId === siteId);
}
