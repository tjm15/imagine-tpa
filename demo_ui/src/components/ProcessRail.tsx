import { CheckCircle, Clock, Circle, FileText, AlertCircle, ChevronDown } from 'lucide-react';
import { WorkspaceMode } from '../App';
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import { Badge } from "./ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { useState } from 'react';

interface ProcessRailProps {
  workspace: WorkspaceMode;
}

export function ProcessRail({ workspace }: ProcessRailProps) {
  const [isOpen, setIsOpen] = useState(true);

  if (workspace === 'plan') {
    return (
      <div className="h-full flex flex-col bg-slate-50/30">
        <div className="p-4 border-b border-slate-200 bg-white">
          <h3 className="text-sm font-semibold text-slate-900">Programme Board</h3>
          <p className="text-xs text-slate-500 mt-0.5">CULP 30-month process</p>
        </div>
        
        <ScrollArea className="flex-1">
          <div className="p-4 space-y-6 relative">
             {/* Timeline Line */}
             <div className="absolute left-[21px] top-4 bottom-4 w-px bg-slate-200" />

            <div className="relative pl-8">
              <div className="absolute left-0 top-0.5 w-4 h-4 rounded-full bg-emerald-100 flex items-center justify-center border border-white shadow-sm z-10">
                <CheckCircle className="w-3 h-3 text-emerald-600" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-slate-900">Notice & Boundary</span>
                <span className="text-xs text-slate-500">Complete</span>
              </div>
            </div>

            <div className="relative pl-8">
              <div className="absolute left-0 top-0.5 w-4 h-4 rounded-full bg-emerald-100 flex items-center justify-center border border-white shadow-sm z-10">
                <CheckCircle className="w-3 h-3 text-emerald-600" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-slate-900">Timetable</span>
                <span className="text-xs text-slate-500">Published Feb 2025</span>
              </div>
            </div>

            <div className="relative pl-8">
              <div className="absolute left-0 top-0.5 w-4 h-4 rounded-full bg-emerald-100 flex items-center justify-center border border-white shadow-sm z-10">
                <CheckCircle className="w-3 h-3 text-emerald-600" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-slate-900">Gateway 1</span>
                <span className="text-xs text-slate-500">Passed Mar 2025</span>
              </div>
            </div>

            <div className="relative pl-0 group">
              <div className="bg-white border border-blue-200 rounded-lg p-3 shadow-sm relative z-10 ml-2">
                 <div className="absolute -left-3 top-4 w-4 h-4 rounded-full bg-blue-100 flex items-center justify-center ring-4 ring-slate-50 z-10">
                    <Clock className="w-3 h-3 text-blue-600 animate-pulse" />
                 </div>
                 
                 <div className="mb-2">
                    <span className="text-sm font-bold text-blue-900 block">Baseline & Place</span>
                    <Badge variant="secondary" className="bg-blue-50 text-blue-700 hover:bg-blue-50 text-[10px] px-1.5 h-5 border-blue-100">In Progress</Badge>
                 </div>

                 <div className="space-y-2 pl-1 border-l-2 border-slate-100 ml-0.5">
                    <div className="flex items-center gap-2 pl-2">
                        <CheckCircle className="w-3 h-3 text-emerald-600" />
                        <span className="text-xs text-slate-600">Place Portrait Draft</span>
                    </div>
                    <div className="flex items-center gap-2 pl-2">
                        <Clock className="w-3 h-3 text-blue-500" />
                        <span className="text-xs text-slate-900 font-medium">Transport Baseline</span>
                    </div>
                    <div className="flex items-center gap-2 pl-2">
                        <Circle className="w-3 h-3 text-slate-300" />
                        <span className="text-xs text-slate-400">SEA Screening</span>
                    </div>
                 </div>
              </div>
            </div>

            <div className="relative pl-8 opacity-60">
              <div className="absolute left-0 top-0.5 w-4 h-4 rounded-full bg-slate-100 flex items-center justify-center border border-slate-300 z-10">
                <Circle className="w-3 h-3 text-slate-400" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-slate-600">Vision & Outcomes</span>
                <span className="text-xs text-slate-400">Due Jul 2025</span>
              </div>
            </div>

            <div className="relative pl-8 opacity-60">
              <div className="absolute left-0 top-0.5 w-4 h-4 rounded-full bg-slate-100 flex items-center justify-center border border-slate-300 z-10">
                <Circle className="w-3 h-3 text-slate-400" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-slate-600">Sites Stage 1</span>
                <span className="text-xs text-slate-400">Due Sep 2025</span>
              </div>
            </div>
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-slate-200 bg-slate-50/50">
          <div className="bg-amber-50 rounded-md border border-amber-100 p-3 shadow-sm">
            <h4 className="text-xs font-semibold text-amber-800 mb-1 flex items-center gap-1.5">
                <AlertCircle className="w-3 h-3" /> Critical Path
            </h4>
            <p className="text-[11px] text-amber-900/80 leading-snug">Transport baseline blocks Vision stage. Commission DfT connectivity analysis.</p>
          </div>
        </div>
      </div>
    );
  }

  // Casework workspace
  return (
    <div className="h-full flex flex-col bg-slate-50/30">
      <div className="p-4 border-b border-slate-200 bg-white">
        <h3 className="text-sm font-semibold text-slate-900">Case File</h3>
        <p className="text-xs text-slate-500 mt-0.5 font-mono">24/0456/FUL</p>
      </div>
      
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
            
            <section>
                <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-3">Current Status</h4>
                <div className="bg-white rounded-lg border border-slate-200 p-3 shadow-sm">
                    <div className="flex items-center gap-2 mb-3">
                         <div className="bg-orange-100 p-1.5 rounded-full">
                            <Clock className="w-4 h-4 text-orange-600" />
                         </div>
                         <div>
                             <p className="text-sm font-medium text-slate-900">Assessment</p>
                             <p className="text-xs text-slate-500">In Progress</p>
                         </div>
                    </div>
                    <div className="bg-orange-50 text-orange-800 text-xs px-2 py-1.5 rounded flex items-center gap-1.5 font-medium border border-orange-100/50">
                        <AlertCircle className="w-3 h-3" />
                        12 days remaining
                    </div>
                </div>
            </section>

            <section>
                <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-3">Key Dates</h4>
                <div className="space-y-2.5">
                    <div className="flex justify-between items-center text-xs">
                        <span className="text-slate-500">Validated</span>
                        <span className="font-medium text-slate-700">15 Nov 2024</span>
                    </div>
                    <div className="flex justify-between items-center text-xs">
                        <span className="text-slate-500">Consultation ends</span>
                        <span className="font-medium text-slate-700">6 Dec 2024</span>
                    </div>
                    <Separator />
                    <div className="flex justify-between items-center text-xs">
                        <span className="text-slate-500">Determination due</span>
                        <Badge variant="outline" className="border-red-200 text-red-700 bg-red-50 text-[10px] px-1.5">31 Dec 2024</Badge>
                    </div>
                </div>
            </section>

            <section>
                <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-3">Consultees</h4>
                <div className="space-y-2">
                    <div className="flex items-center justify-between p-2 rounded bg-white border border-slate-100 shadow-sm">
                        <span className="text-xs text-slate-700">Highways</span>
                        <Badge className="bg-emerald-50 text-emerald-700 hover:bg-emerald-50 border-emerald-100 h-5 text-[10px]">Responded</Badge>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded bg-white border border-slate-100 shadow-sm">
                        <span className="text-xs text-slate-700">Conservation</span>
                        <Badge className="bg-emerald-50 text-emerald-700 hover:bg-emerald-50 border-emerald-100 h-5 text-[10px]">Responded</Badge>
                    </div>
                    <div className="flex items-center justify-between p-2 rounded bg-white border border-slate-100 shadow-sm">
                        <span className="text-xs text-slate-700">Env. Health</span>
                        <Badge variant="outline" className="text-slate-500 h-5 text-[10px] border-dashed">Pending</Badge>
                    </div>
                </div>
            </section>

            <section>
                <h4 className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-3">Revisions</h4>
                <div className="space-y-2">
                    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
                         <div className="flex items-center gap-2 mb-2">
                             <CollapsibleTrigger className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
                                 <ChevronDown className={`w-3 h-3 transition-transform ${isOpen ? '' : '-rotate-90'}`} />
                                 History
                             </CollapsibleTrigger>
                         </div>
                         <CollapsibleContent className="space-y-2">
                            <div className="text-xs p-2.5 bg-white border border-slate-200 rounded shadow-sm">
                                <div className="text-slate-900 font-medium mb-0.5">Rev A: Amended elevations</div>
                                <div className="text-slate-500 text-[10px]">Received 2 Dec 2024</div>
                            </div>
                            <div className="text-xs p-2.5 bg-slate-100 border border-slate-200 rounded opacity-60">
                                <div className="text-slate-700 font-medium mb-0.5">Original submission</div>
                                <div className="text-slate-500 text-[10px]">Received 1 Nov 2024</div>
                            </div>
                         </CollapsibleContent>
                    </Collapsible>
                </div>
            </section>
        </div>
      </ScrollArea>
      
      <div className="p-4 border-t border-slate-200 bg-slate-50">
        <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-xs">
                SM
            </div>
            <div>
                 <div className="text-sm font-medium text-slate-900">Sarah Mitchell</div>
                 <div className="text-xs text-slate-500">Case Officer</div>
            </div>
        </div>
      </div>
    </div>
  );
}
