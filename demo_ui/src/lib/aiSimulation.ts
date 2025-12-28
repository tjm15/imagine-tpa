/**
 * AI Simulation Engine
 * 
 * Provides realistic AI response simulation for the demo including:
 * - Streaming text generation with typing effect
 * - Context-aware suggestions based on current stage
 * - Gateway check simulations with warnings
 * - Balance completion with synthesised reasoning
 * - Inspector question generation
 */

import { ReasoningMove, Consideration } from '../fixtures/mockData';

// ============================================================================
// TYPES
// ============================================================================

export interface AIResponse {
  text: string;
  confidence: 'high' | 'medium' | 'low';
  citations?: string[];
  warnings?: string[];
  suggestions?: string[];
}

export interface GatewayCheckResult {
  passed: boolean;
  score: number;
  gaps: Array<{ area: string; severity: 'critical' | 'major' | 'minor'; description: string }>;
  strengths: string[];
  recommendations: string[];
  inspectorQuestions: string[];
}

export interface BalanceResult {
  position: string;
  confidence: 'high' | 'medium' | 'low';
  reasoning: string;
  forConsiderations: string[];
  againstConsiderations: string[];
  tensions: string[];
  conditions: string[];
}

// ============================================================================
// MOCK AI RESPONSES BY STAGE
// ============================================================================

const stageDraftResponses: Record<string, string[]> = {
  'baseline': [
    `## Housing Market Overview

Cambridge faces acute housing pressure with an affordability ratio of 12.8x, significantly exceeding the regional average of 8.2x. This represents a deterioration from 10.5x in 2015, indicating a worsening trend.

**Key indicators:**
- Current housing stock: 52,400 dwellings
- Tenure split: 48% owner-occupied, 28% private rented, 24% social rented
- 5-year delivery average: 1,240 dpa against a target of 1,800 dpa

The housing market exhibits characteristics of severe undersupply relative to demand, driven by Cambridge's role as a knowledge economy hub with strong employment growth.`,

    `## Transport and Connectivity Baseline

Cambridge benefits from strong sustainable transport connectivity:

**Rail:** Direct services to London King's Cross in 50 minutes, with frequent connections to Stansted Airport and regional centres.

**Cycling:** Extensive network of 142km of dedicated cycleways, with modal share of 28% for commuting - among the highest in England.

**Bus:** 78% of residents within 400m of frequent bus services.

**Constraints:** Strategic road capacity remains limited, particularly on the A14 corridor where peak hour congestion affects journey reliability.

*Note: DfT Connectivity Tool outputs do not model capacity constraints or future growth scenarios.*`,

    `## Environmental Context

The Cambridge authority area contains significant environmental assets requiring consideration in plan-making:

**Designated Sites:**
- Cambridge Green Belt (47% of authority area)
- Gog Magog Hills AONB candidate area
- 12 Sites of Special Scientific Interest
- River Cam corridor and associated washlands

**Climate Considerations:**
- Flood Zone 2/3 coverage: 8% of authority area
- Cambridge Water stress area classification
- Heat island effect in urban core

**Biodiversity:**
- Local Wildlife Sites network
- Great crested newt population licensing areas
- Ancient woodland pockets`,
  ],

  'vision': [
    `## Vision Statement

By 2040, Cambridge will be a thriving, inclusive city that balances its world-leading role in research and innovation with the needs of all its residents. We will have:

**Created genuinely affordable homes** across all tenures, addressing the housing crisis through sensitive intensification and strategic growth that respects our historic character.

**Achieved carbon neutrality** through exemplary sustainable development, active travel networks, and nature-positive planning.

**Strengthened our communities** by ensuring new development delivers schools, healthcare, green spaces and cultural facilities that serve existing and future residents.

**Protected what makes Cambridge special** - our historic core, green spaces, and the relationship between town and gown - while accommodating necessary change.`,

    `## Strategic Outcomes (Draft)

1. **Housing for All**: Deliver at least 1,800 homes per year with 40% affordable, including family homes and specialist provision.

2. **Zero Carbon by 2040**: All new development net zero in operation; 20% reduction in transport emissions.

3. **Connected Neighbourhoods**: 15-minute neighbourhood principles applied to all allocations; no resident more than 800m from local services.

4. **Green Cambridge**: 20% biodiversity net gain; no net loss of green belt; urban greening factor of 0.4 minimum.

5. **Thriving Economy**: Safeguard and grow knowledge economy; 10,000 new jobs in sustainable sectors.`,
  ],

  'sites': [
    `## Site Assessment: SHLAA/045 Northern Fringe

**Location:** Land north of Milton Road, Cambridge
**Size:** 12.4 hectares
**Proposed capacity:** 450 dwellings

### Suitability Assessment

**Positive factors:**
- Previously developed land (former mineral workings)
- Strong public transport accessibility (Guided Busway stop within 400m)
- Outside Conservation Area
- No flood risk (Zone 1)

**Constraints:**
- Partially within Green Belt (eastern portion)
- Adjacent to Cambridge Science Park (noise/amenity interface)
- Requires remediation (contaminated land)
- Heritage asset proximity (Grade II listed farm building 150m east)

### Achievability

**Viability:** Remediation costs estimated £2.4m; viable at current land values with 35% affordable.
**Deliverability:** Available now; developer interest confirmed; could deliver years 3-7.

### Recommendation

Include in shortlist for Regulation 18 consultation subject to:
- Green Belt exceptional circumstances assessment
- Noise mitigation strategy
- Heritage setting assessment`,
  ],

  'gateway': [
    `## Gateway 2 Self-Assessment Summary

### Evidence Base Completeness

| Topic | Status | Notes |
|-------|--------|-------|
| Housing need | ✅ Complete | SHMA 2024 adopted |
| Employment | ✅ Complete | ELR updated Q2 2024 |
| Transport | ⚠️ Gaps | Strategic model not updated for preferred option |
| Environment | ✅ Complete | HRA screening complete |
| Heritage | ⚠️ Minor gaps | Conservation area appraisals need updating |
| Viability | ✅ Complete | Whole plan viability October 2024 |

### Reasonable Alternatives

5 spatial strategy options tested with SA/SEA matrix. Preferred option (hybrid urban intensification + strategic edge site) performs best against housing delivery and sustainability objectives.

### Risks for Examination

1. **Transport evidence timing** - Inspector may question whether strategic modelling reflects final allocations
2. **Green Belt release** - Exceptional circumstances case requires strengthening
3. **Duty to Cooperate** - Statement of Common Ground with South Cambridgeshire needs finalising`,
  ],
};

const stageSpecificSuggestions: Record<string, Array<{
  id: string;
  type: 'content' | 'evidence' | 'warning' | 'question';
  text: string;
  context: string;
  confidence: 'high' | 'medium' | 'low';
}>> = {
  'baseline': [
    {
      id: 'sug-1',
      type: 'evidence',
      text: 'Consider adding ONS population projections (2021-based) to support housing need analysis',
      context: 'Housing Market section',
      confidence: 'high',
    },
    {
      id: 'sug-2',
      type: 'warning',
      text: 'Transport baseline incomplete - DfT data does not include capacity analysis. Consider commissioning strategic transport model.',
      context: 'Evidence gaps',
      confidence: 'high',
    },
    {
      id: 'sug-3',
      type: 'question',
      text: 'Should the place portrait reference the Cambridge-Milton Keynes-Oxford Arc proposals?',
      context: 'Strategic context',
      confidence: 'medium',
    },
  ],
  'vision': [
    {
      id: 'sug-4',
      type: 'warning',
      text: 'Outcome 3 (Connected Neighbourhoods) may conflict with Outcome 5 (Thriving Economy) if employment growth is concentrated in existing business parks.',
      context: 'Outcomes coherence',
      confidence: 'medium',
    },
    {
      id: 'sug-5',
      type: 'content',
      text: 'Vision statement currently 180 words. Government guidance suggests keeping under 150 for clarity.',
      context: 'Document length',
      confidence: 'low',
    },
  ],
  'sites': [
    {
      id: 'sug-6',
      type: 'warning',
      text: 'Site SHLAA/045 allocation boundary overlaps Conservation Area by 0.3ha. Boundary adjustment recommended.',
      context: 'Spatial accuracy',
      confidence: 'high',
    },
    {
      id: 'sug-7',
      type: 'evidence',
      text: 'Flooding constraint on SHLAA/067 based on 2019 data. EA published updated modelling in 2024 - recommend refresh.',
      context: 'Evidence currency',
      confidence: 'high',
    },
  ],
  'gateway': [
    {
      id: 'sug-8',
      type: 'question',
      text: 'Inspector likely to question: How does the preferred spatial strategy respond to the climate emergency declaration?',
      context: 'Examination preparation',
      confidence: 'high',
    },
    {
      id: 'sug-9',
      type: 'warning',
      text: 'Soundness risk: Alternatives assessment for employment allocations appears thin. Only 2 options tested vs. 5 for housing.',
      context: 'SA/SEA completeness',
      confidence: 'high',
    },
  ],
};

const inspectorQuestions: Record<string, string[]> = {
  'housing': [
    'How does the housing requirement of 1,800 dpa relate to the standard method calculation?',
    'What evidence supports the assumption that 35% affordable housing is viable across all allocated sites?',
    'How have you addressed the needs of older persons and students in your housing mix policies?',
  ],
  'greenBelt': [
    'What exceptional circumstances justify the release of Green Belt land at [site]?',
    'Have you considered alternative strategies that would avoid Green Belt release?',
    'How does the proposed Green Belt release align with NPPF paragraph 145?',
  ],
  'transport': [
    'What assumptions underpin the transport modelling for the preferred spatial strategy?',
    'How confident are you that the A14 junction improvements will be funded and delivered?',
    'What is the modal split assumption for new development, and how will this be secured?',
  ],
  'soundness': [
    'Is the plan positively prepared in terms of meeting objectively assessed needs?',
    'How have you ensured the plan is justified as the most appropriate strategy?',
    'What monitoring indicators will you use to assess plan effectiveness?',
  ],
};

// ============================================================================
// SIMULATION FUNCTIONS
// ============================================================================

/**
 * Simulates streaming AI text generation with realistic typing effect
 */
export async function simulateDraft(
  stageId: string,
  onStream: (text: string, progress: number) => void,
  onComplete: () => void
): Promise<AIResponse> {
  const responses = stageDraftResponses[stageId] || stageDraftResponses['baseline'];
  const fullText = responses[Math.floor(Math.random() * responses.length)];
  
  const words = fullText.split(' ');
  let currentText = '';
  
  for (let i = 0; i < words.length; i++) {
    currentText += (i > 0 ? ' ' : '') + words[i];
    const progress = Math.round((i / words.length) * 100);
    onStream(currentText, progress);
    
    // Variable delay for realistic feel
    const delay = Math.random() * 30 + 10; // 10-40ms per word
    await new Promise(resolve => setTimeout(resolve, delay));
  }
  
  onComplete();
  
  return {
    text: fullText,
    confidence: 'medium',
    citations: ['ev-census-2021', 'ev-affordability'],
    suggestions: ['Consider adding comparative data from similar authorities'],
  };
}

/**
 * Returns context-aware suggestions for current stage
 */
export function getStageSuggestions(stageId: string) {
  return stageSpecificSuggestions[stageId] || [];
}

/**
 * Simulates a gateway check with detailed results
 */
export async function simulateGatewayCheck(
  gateway: 1 | 2 | 3,
  onProgress: (progress: number, message: string) => void
): Promise<GatewayCheckResult> {
  const steps = [
    'Checking evidence base completeness...',
    'Analysing alternatives coverage...',
    'Reviewing policy alignment...',
    'Simulating inspector scrutiny...',
    'Generating recommendations...',
  ];

  for (let i = 0; i < steps.length; i++) {
    onProgress(Math.round(((i + 1) / steps.length) * 100), steps[i]);
    await new Promise(resolve => setTimeout(resolve, 800 + Math.random() * 400));
  }

  // Simulate different results based on gateway
  const baseResult: GatewayCheckResult = {
    passed: gateway < 3,
    score: gateway === 1 ? 78 : gateway === 2 ? 72 : 65,
    gaps: [],
    strengths: [],
    recommendations: [],
    inspectorQuestions: [],
  };

  if (gateway >= 1) {
    baseResult.gaps.push({
      area: 'Transport Evidence',
      severity: 'major',
      description: 'Strategic transport model not updated to reflect preferred spatial strategy.',
    });
    baseResult.strengths.push('Housing need evidence robust and up-to-date (SHMA 2024)');
    baseResult.recommendations.push('Commission transport modelling update before Gateway 2');
  }

  if (gateway >= 2) {
    baseResult.gaps.push({
      area: 'Green Belt',
      severity: 'critical',
      description: 'Exceptional circumstances case for GB release requires strengthening.',
    });
    baseResult.gaps.push({
      area: 'Heritage',
      severity: 'minor',
      description: 'Conservation area appraisals need updating for affected allocations.',
    });
    baseResult.strengths.push('Comprehensive alternatives assessment for housing strategy');
    baseResult.recommendations.push('Prepare Green Belt Topic Paper with detailed exceptional circumstances');
  }

  if (gateway >= 3) {
    baseResult.inspectorQuestions = [
      ...inspectorQuestions['housing'].slice(0, 2),
      ...inspectorQuestions['greenBelt'].slice(0, 1),
      ...inspectorQuestions['soundness'].slice(0, 1),
    ];
  }

  return baseResult;
}

/**
 * Simulates planning balance completion
 */
export async function simulateBalance(
  considerations: Consideration[],
  framingId: string,
  onStream: (text: string, progress: number) => void,
  onComplete: () => void
): Promise<BalanceResult> {
  const forConsiderations = considerations.filter(c => c.direction === 'supports');
  const againstConsiderations = considerations.filter(c => c.direction === 'against');
  
  const framingLabels: Record<string, string> = {
    'high-growth': 'growth-focused',
    'heritage-balanced': 'heritage-balanced',
    'climate-nature': 'climate-first',
  };
  const framingLabel = framingLabels[framingId] || 'balanced';

  const balanceText = `## Planning Balance

Under a **${framingLabel}** framing, the balance tips in favour of **approval with conditions**.

### Considerations in Favour (${forConsiderations.length})

${forConsiderations.map(c => `- **${c.issue}** (${c.weight} weight): ${c.summary || 'Supports the proposal based on linked evidence and policy.'}`).join('\n')}

### Considerations Against (${againstConsiderations.length})

${againstConsiderations.map(c => `- **${c.issue}** (${c.weight} weight): ${c.summary || 'Raises concerns requiring mitigation.'}`).join('\n')}

### Tensions Identified

The most significant tension exists between housing delivery imperatives and heritage protection. Under the selected framing, housing need is given priority, but the scheme must demonstrate high design quality to be acceptable.

### Conclusion

A reasonable planning authority, properly directing itself, could approve this application subject to:
1. Secure cycle storage condition
2. Materials to match conservation area palette
3. Section 106 for local employment during construction

*This balance is conditional on the stated political framing. Alternative framings would produce different weights and potentially different conclusions.*`;

  const words = balanceText.split(' ');
  let currentText = '';
  
  for (let i = 0; i < words.length; i++) {
    currentText += (i > 0 ? ' ' : '') + words[i];
    onStream(currentText, Math.round((i / words.length) * 100));
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  
  onComplete();

  return {
    position: 'Approve with conditions',
    confidence: 'medium',
    reasoning: balanceText,
    forConsiderations: forConsiderations.map(c => c.id),
    againstConsiderations: againstConsiderations.map(c => c.id),
    tensions: ['Housing vs Heritage'],
    conditions: ['Cycle storage', 'Materials condition', 'S106 local employment'],
  };
}

/**
 * Generates anticipated inspector questions
 */
export function generateInspectorQuestions(topics: string[]): string[] {
  const questions: string[] = [];
  
  for (const topic of topics) {
    const topicQuestions = inspectorQuestions[topic] || [];
    questions.push(...topicQuestions.slice(0, 2));
  }
  
  return questions.slice(0, 5);
}

/**
 * Simulates AI accepting/processing a dropped evidence card
 */
export async function processDroppedEvidence(
  evidenceId: string,
  context: string
): Promise<{ citation: string; suggestion: string }> {
  await new Promise(resolve => setTimeout(resolve, 500));
  
  const citationFormats: Record<string, string> = {
    'ev-census-2021': '[Census 2021, ONS]',
    'ev-affordability': '[ONS House Price Statistics, Q3 2024]',
    'ev-shlaa-2024': '[SHLAA 2024, Cambridge City Council]',
    'ev-transport-dft': '[DfT Connectivity Tool, 2024]',
    'ev-site-visit': '[Site Visit Record, Dec 2024]',
    'ev-marketing': '[Marketing Evidence, Oct 2024]',
  };

  const suggestions: Record<string, string> = {
    'ev-census-2021': 'Consider adding comparison with regional tenure patterns.',
    'ev-affordability': 'This evidence supports a finding of acute housing pressure.',
    'ev-shlaa-2024': 'Note the deliverability caveats in the SHLAA methodology.',
    'ev-transport-dft': 'Caveat: DfT tool does not model capacity constraints.',
    'ev-site-visit': 'Site visit evidence is strong - consider adding photos.',
    'ev-marketing': 'Marketing evidence meets policy threshold (12 months).',
  };

  return {
    citation: citationFormats[evidenceId] || `[${evidenceId}]`,
    suggestion: suggestions[evidenceId] || 'Evidence cited successfully.',
  };
}
