import { 
  CheckCircle, Clock, Circle, ArrowRight, HelpCircle,
  FileSearch, Lightbulb, Scale, MessageSquare, FileText
} from 'lucide-react';
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";

export type ReasoningMove = 
  | 'framing' 
  | 'issues' 
  | 'evidence' 
  | 'interpretation' 
  | 'considerations' 
  | 'balance' 
  | 'negotiation' 
  | 'positioning';

interface MoveInfo {
  label: string;
  question: string;
  icon: typeof Scale;
  color: string;
}

const moveDetails: Record<ReasoningMove, MoveInfo> = {
  framing: { 
    label: 'Framing', 
    question: 'What are we trying to achieve?',
    icon: Lightbulb,
    color: 'purple'
  },
  issues: { 
    label: 'Issues', 
    question: 'What matters here?',
    icon: HelpCircle,
    color: 'blue'
  },
  evidence: { 
    label: 'Evidence', 
    question: 'What do we know?',
    icon: FileSearch,
    color: 'cyan'
  },
  interpretation: { 
    label: 'Interpretation', 
    question: 'What does it mean?',
    icon: Lightbulb,
    color: 'teal'
  },
  considerations: { 
    label: 'Considerations', 
    question: 'What weighs in the balance?',
    icon: Scale,
    color: 'emerald'
  },
  balance: { 
    label: 'Balance', 
    question: 'How do we weigh it up?',
    icon: Scale,
    color: 'amber'
  },
  negotiation: { 
    label: 'Negotiation', 
    question: 'What could make it work?',
    icon: MessageSquare,
    color: 'orange'
  },
  positioning: { 
    label: 'Position', 
    question: 'What\'s our recommendation?',
    icon: FileText,
    color: 'rose'
  }
};

const moveOrder: ReasoningMove[] = [
  'framing', 'issues', 'evidence', 'interpretation', 
  'considerations', 'balance', 'negotiation', 'positioning'
];

interface ReasoningProgressProps {
  moveStatus: Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'>;
  onMoveClick?: (move: ReasoningMove) => void;
}

export function ReasoningProgressBar({ 
  moveStatus, 
  onMoveClick 
}: ReasoningProgressProps) {
  const currentMove = moveOrder.find(m => moveStatus[m] === 'in-progress') || 'framing';
  const currentInfo = moveDetails[currentMove];

  return (
    <ScrollArea className="h-full">
      <div className="p-4">
        {/* Current Step Hero */}
        <div className="mb-6 p-4 rounded-xl bg-gradient-to-r from-slate-50 to-white border border-slate-200 shadow-sm">
          <div className="flex items-start gap-3">
            <div className={`p-2.5 rounded-lg bg-${currentInfo.color}-100`}>
              <currentInfo.icon className={`w-5 h-5 text-${currentInfo.color}-600`} />
            </div>
            <div className="flex-1">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
                Currently working on
              </p>
              <h3 className="text-lg font-semibold text-slate-900 mb-1">
                {currentInfo.label}
              </h3>
              <p className="text-sm text-slate-600">
                {currentInfo.question}
              </p>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <Button size="sm" variant="outline" className="text-xs">
              View Details
            </Button>
            <Button size="sm" className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white">
              Mark Complete
            </Button>
          </div>
        </div>

        {/* Progress Steps */}
        <div className="space-y-1">
          <TooltipProvider>
            {moveOrder.map((move, idx) => {
              const info = moveDetails[move];
              const status = moveStatus[move];
              const Icon = info.icon;
              const isActive = status === 'in-progress';
              const isComplete = status === 'complete';
              
              return (
                <Tooltip key={move}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onMoveClick?.(move)}
                      className={`w-full flex items-center gap-3 p-2 rounded-lg transition-all ${
                        isActive 
                          ? 'bg-amber-50 border border-amber-200' 
                          : isComplete
                            ? 'bg-emerald-50/50 hover:bg-emerald-50'
                            : 'hover:bg-slate-50'
                      }`}
                    >
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                        isComplete
                          ? 'bg-emerald-100'
                          : isActive
                            ? 'bg-amber-100 ring-2 ring-amber-300 ring-offset-1'
                            : 'bg-slate-100'
                      }`}>
                        {isComplete ? (
                          <CheckCircle className="w-4 h-4 text-emerald-600" />
                        ) : isActive ? (
                          <Clock className="w-4 h-4 text-amber-600" />
                        ) : (
                          <span className="text-xs text-slate-400 font-medium">{idx + 1}</span>
                        )}
                      </div>
                      
                      <div className="flex-1 text-left">
                        <p className={`text-sm font-medium ${
                          isActive 
                            ? 'text-amber-800' 
                            : isComplete 
                              ? 'text-emerald-700' 
                              : 'text-slate-500'
                        }`}>
                          {info.label}
                        </p>
                      </div>
                      
                      {isComplete && (
                        <CheckCircle className="w-4 h-4 text-emerald-500" />
                      )}
                      {isActive && (
                        <span className="px-2 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-700 rounded-full">
                          In progress
                        </span>
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">
                    <p className="font-medium">{info.label}</p>
                    <p className="text-xs text-slate-400">{info.question}</p>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </TooltipProvider>
        </div>
      </div>
    </ScrollArea>
  );
}
