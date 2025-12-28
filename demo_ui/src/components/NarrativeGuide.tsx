import { useMemo } from 'react';
import { 
  Lightbulb, 
  Copy, 
  ArrowRight, 
  HelpCircle, 
  CheckCircle2, 
  BookOpen,
  List,
  Scale,
  MessageSquare
} from 'lucide-react';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { useAppState } from '../lib/appState';

interface NarrativeGuideProps {
  onInsertTemplate: (template: string) => void;
}

type ReasoningMove = 'framing' | 'issues' | 'evidence' | 'interpretation' | 'considerations' | 'balance' | 'negotiation' | 'positioning';

interface MoveGuide {
  title: string;
  icon: React.ElementType;
  goal: string;
  questions: string[];
  template: string;
}

const GUIDES: Record<ReasoningMove, MoveGuide> = {
  framing: {
    title: 'Framing',
    icon: Lightbulb,
    goal: 'Establish the "lens" and scope for this document.',
    questions: [
      'What is the primary purpose of this document?',
      'What are the key political or strategic objectives?',
      'What assumptions are we making at the start?'
    ],
    template: `<h2>1. Purpose & Scope</h2>
<p>The purpose of this document is to [purpose]...</p>
<h3>Strategic Objectives</h3>
<ul>
  <li>Objective 1: ...</li>
  <li>Objective 2: ...</li>
</ul>
<h3>Key Assumptions</h3>
<p>This assessment assumes...</p>`
  },
  issues: {
    title: 'Issue Surfacing',
    icon: HelpCircle,
    goal: 'Identify what is material to this decision.',
    questions: [
      'What are the main planning issues?',
      'Are there specific site constraints?',
      'What policy designations apply?'
    ],
    template: `<h2>2. Key Issues</h2>
<p>The following material considerations have been identified:</p>
<ul>
  <li><strong>Principle of Development:</strong> ...</li>
  <li><strong>Heritage Impact:</strong> ...</li>
  <li><strong>Transport & Access:</strong> ...</li>
</ul>`
  },
  evidence: {
    title: 'Evidence Curation',
    icon: BookOpen,
    goal: 'Gather facts required to assess the issues.',
    questions: [
      'What data sources support our assessment?',
      'Are there gaps in the evidence?',
      'What technical studies have been commissioned?'
    ],
    template: `<h2>3. Evidence Base</h2>
<p>This assessment relies on the following evidence:</p>
<ul>
  <li>Census 2021 Data</li>
  <li>Strategic Housing Land Availability Assessment (SHLAA)</li>
  <li>Transport Assessment (2024)</li>
</ul>
<p><em>Note: Limitations in the transport data regarding...</em></p>`
  },
  interpretation: {
    title: 'Interpretation',
    icon: MessageSquare,
    goal: 'Make sense of evidence using tests and heuristics.',
    questions: [
      'What does the evidence tell us about each issue?',
      'Are statutory tests met?',
      'How do we interpret conflicting data?'
    ],
    template: `<h3>Assessment of Transport Impact</h3>
<p>The evidence suggests that while trip generation is within limits, the cumulative impact on the A14 junction requires mitigation...</p>
<h3>Heritage Impact Assessment</h3>
<p>The impact on the Conservation Area is assessed as 'less than substantial' because...`
  },
  considerations: {
    title: 'Considerations',
    icon: List,
    goal: 'Form the "bricks" of the planning argument.',
    questions: [
      'What are the positive factors (benefits)?',
      'What are the negative factors (harms)?',
      'Are there direct policy conflicts?'
    ],
    template: `<h2>4. Planning Balance Considerations</h2>
<h3>Benefits (For)</h3>
<ul>
  <li>Delivery of 45 affordable homes (Significant weight)</li>
  <li>Biodiversity net gain of 15% (Moderate weight)</li>
</ul>
<h3>Harms (Against)</h3>
<ul>
  <li>Loss of Grade 3 agricultural land (Limited weight)</li>
  <li>Visual impact on open countryside (Moderate weight)</li>
</ul>`
  },
  balance: {
    title: 'Weighing & Balance',
    icon: Scale,
    goal: 'Assign weight and determine the outcome.',
    questions: [
      'Is the "tilted balance" engaged?',
      'Do benefits outweigh harms?',
      'What is the decisive factor?'
    ],
    template: `<h2>5. The Planning Balance</h2>
<p>Section 38(6) requires determination in accordance with the development plan unless material considerations indicate otherwise.</p>
<p><strong>Conclusion:</strong> The significant benefits of affordable housing delivery are considered to outweigh the moderate harm to landscape character, particularly given...</p>`
  },
  negotiation: {
    title: 'Negotiation',
    icon: MessageSquare,
    goal: 'Propose changes to resolve conflicts.',
    questions: [
      'Can harms be mitigated by condition?',
      'Is a S106 agreement required?',
      'What changes would make this acceptable?'
    ],
    template: `<h3>Recommended Conditions / Obligations</h3>
<ul>
  <li>Condition: Construction Management Plan</li>
  <li>S106: Contribution to local education provision (£450k)</li>
</ul>`
  },
  positioning: {
    title: 'Positioning',
    icon: CheckCircle2,
    goal: 'Tell the final story and recommendation.',
    questions: [
      'What is the final recommendation?',
      'Is the narrative coherent?',
      'Is the decision robust to challenge?'
    ],
    template: `<h2>6. Recommendation</h2>
<p><strong>APPROVE</strong> subject to the conditions and obligations set out above.</p>`
  }
};

// Helper to get the current move from app state
function useCurrentMove(): ReasoningMove {
  const { reasoningMoves } = useAppState();
  const moveOrder: ReasoningMove[] = [
    'framing', 'issues', 'evidence', 'interpretation', 
    'considerations', 'balance', 'negotiation', 'positioning'
  ];
  
  // Find first in-progress move, or last completed, or default to framing
  const current = moveOrder.find(m => reasoningMoves[m] === 'in-progress');
  if (current) return current;
  
  const lastCompleted = [...moveOrder].reverse().find(m => reasoningMoves[m] === 'complete');
  return lastCompleted || 'framing';
}

export function NarrativeGuide({ onInsertTemplate }: NarrativeGuideProps) {
  const currentMove = useCurrentMove();
  const guide = GUIDES[currentMove];

  return (
    <Card className="h-full border-l-0 rounded-none shadow-none bg-slate-50/50">
      <CardHeader className="px-4 pt-4 pb-3">
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 uppercase text-[10px] tracking-wider">
            Current Move
          </Badge>
        </div>
        <CardTitle className="text-lg flex items-center gap-2">
          <guide.icon className="w-5 h-5 text-slate-500" />
          {guide.title}
        </CardTitle>
        <CardDescription className="text-xs mt-1">
          {guide.goal}
        </CardDescription>
      </CardHeader>
      
      <ScrollArea className="flex-1 px-4">
        <div className="space-y-6 pb-6">
          {/* Key Questions */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-slate-900 flex items-center gap-2">
              <HelpCircle className="w-4 h-4 text-slate-400" />
              Key Questions
            </h4>
            <ul className="space-y-2">
              {guide.questions.map((q, i) => (
                <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                  <span className="block w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 flex-shrink-0" />
                  {q}
                </li>
              ))}
            </ul>
          </div>

          {/* Template Action */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-slate-900 flex items-center gap-2">
              <Copy className="w-4 h-4 text-slate-400" />
              Suggested Structure
            </h4>
            <div className="bg-white border rounded-md p-3">
              <div
                className="prose prose-sm prose-slate max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-1 prose-h2:my-2 prose-h3:my-2 prose-h2:text-base prose-h3:text-sm"
                dangerouslySetInnerHTML={{ __html: guide.template }}
              />
              <div className="mt-3 flex justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  className="h-7 text-xs shadow-sm"
                  onClick={() => onInsertTemplate(guide.template)}
                >
                  <ArrowRight className="w-3 h-3 mr-1" />
                  Insert Template
                </Button>
              </div>
            </div>
          </div>
        </div>
      </ScrollArea>
    </Card>
  );
}
