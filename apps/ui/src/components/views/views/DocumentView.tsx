import { WorkspaceMode } from '../../App';
import { FileText, Plus, Link2, MessageSquare, Sparkles, AlertCircle, Info, ChevronRight, CheckCircle } from 'lucide-react';
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";

interface DocumentViewProps {
  workspace: WorkspaceMode;
}

export function DocumentView({ workspace }: DocumentViewProps) {
  const title = workspace === 'plan' 
    ? 'Place Portrait: Baseline Evidence' 
    : 'Officer Report: 24/0456/FUL';

  return (
    <div className="max-w-4xl mx-auto p-8 font-sans">
      {/* Document Header */}
      <div className="mb-10 pb-6 border-b border-slate-200">
        <div className="flex items-center gap-2 text-sm text-blue-600 font-medium mb-3">
          <FileText className="w-4 h-4" />
          <span className="uppercase tracking-wider text-xs">{workspace === 'plan' ? 'Deliverable Document' : 'Officer Report'}</span>
        </div>
        <h1 className="text-4xl font-bold text-slate-900 mb-4 tracking-tight">{title}</h1>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-500">
          <Badge variant="outline" className="bg-slate-50 border-slate-200 text-slate-600 rounded-sm font-normal">Draft v2.3</Badge>
          <span>Last edited 18 Dec 2024</span>
          <span>by <span className="text-slate-900 font-medium">Sarah Mitchell</span></span>
        </div>
      </div>

      {/* Document Content */}
      <div className="space-y-8 max-w-none text-slate-800 leading-relaxed">
        {workspace === 'plan' ? (
          <>
            <section className="space-y-4">
              <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                 <span className="text-slate-300 text-xl font-normal">01</span> Introduction
              </h2>
              <p className="text-lg text-slate-600 leading-relaxed">
                This place portrait provides the baseline evidence for Cambridge's local plan review under the new CULP system. 
                It establishes the current context against which spatial strategy options will be assessed.
              </p>
              <p>
                The portrait draws on multiple evidence sources including Census 2021, local monitoring data, and commissioned 
                technical studies. All limitations are explicitly noted.
              </p>
              
              <div className="flex items-center gap-2 pl-4 border-l-2 border-blue-200 py-1">
                   <Link2 className="w-3.5 h-3.5 text-blue-500" />
                   <span className="text-sm font-medium text-blue-700 cursor-pointer hover:underline">Evidence Source: Census 2021 Data Pack</span>
              </div>
            </section>

            <section className="space-y-6">
              <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2 mt-8">
                  <span className="text-slate-300 text-xl font-normal">02</span> Housing Context
              </h2>
              
              <Card className="bg-slate-50/50 border-slate-200 shadow-sm overflow-hidden">
                 <div className="bg-slate-100/50 px-4 py-2 border-b border-slate-200 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-700">Key Indicators: Housing Market</h3>
                    <Badge variant="secondary" className="bg-white text-slate-500 border-slate-200">Q3 2024</Badge>
                 </div>
                 <CardContent className="p-6">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                        <div>
                            <div className="text-sm text-slate-500 mb-1">Current Stock</div>
                            <div className="text-2xl font-bold text-slate-900">52,400</div>
                            <div className="text-xs text-slate-400">dwellings</div>
                        </div>
                        <div>
                            <div className="text-sm text-slate-500 mb-1">Affordability Ratio</div>
                            <div className="text-2xl font-bold text-orange-600">12.8x</div>
                            <div className="text-xs text-orange-600/80">High Risk</div>
                        </div>
                        <div>
                            <div className="text-sm text-slate-500 mb-1">Delivery (5yr avg)</div>
                            <div className="text-2xl font-bold text-slate-900">1,240</div>
                            <div className="text-xs text-slate-400">dpa</div>
                        </div>
                        <div>
                            <div className="text-sm text-slate-500 mb-1">Target Need</div>
                            <div className="text-2xl font-bold text-slate-900">1,800</div>
                            <div className="text-xs text-slate-400">dpa</div>
                        </div>
                    </div>
                    <Separator className="my-4" />
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Info className="w-3.5 h-3.5" />
                        <span>Source: Census 2021, ONS House Price Statistics, AMR 2023</span>
                    </div>
                 </CardContent>
              </Card>

              <p>
                Cambridge faces acute housing pressure. The affordability ratio of 12.8x significantly exceeds both the regional 
                average (8.2x) and represents a deterioration from 10.5x in 2015.
              </p>
              
               <div className="flex items-center gap-2 pl-4 border-l-2 border-blue-200 py-1">
                   <Link2 className="w-3.5 h-3.5 text-blue-500" />
                   <span className="text-sm font-medium text-blue-700 cursor-pointer hover:underline">Evidence Source: ONS Housing Statistics</span>
              </div>

              <Alert className="bg-blue-50 border-blue-100 text-blue-900">
                 <Sparkles className="h-4 w-4 text-blue-600" />
                 <AlertTitle className="text-blue-800 font-semibold mb-1">AI Suggestion</AlertTitle>
                 <AlertDescription className="text-blue-800/80 text-sm">
                    Consider adding comparison with Cambridge's Knowledge Economy employment growth (3.2% pa) to establish 
                    jobs-housing imbalance context.
                 </AlertDescription>
                 <div className="flex gap-2 mt-3">
                    <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white h-7 text-xs">Accept Suggestion</Button>
                    <Button size="sm" variant="ghost" className="text-blue-600 hover:bg-blue-100 h-7 text-xs">Dismiss</Button>
                 </div>
              </Alert>

              <div className="p-4 bg-amber-50 rounded-lg border border-amber-100 flex gap-3 text-sm text-amber-900">
                 <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0" />
                 <div>
                    <span className="font-semibold text-amber-800">Evidence Gap:</span> Detailed housing needs assessment for specific groups (older persons, students, key workers) 
                    is currently being commissioned. Expected completion: Q1 2025.
                 </div>
              </div>
            </section>

            <section className="space-y-4">
              <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2 mt-8">
                  <span className="text-slate-300 text-xl font-normal">03</span> Transport & Connectivity
              </h2>
              <p>
                Cambridge benefits from strong rail connectivity to London (50 mins) and excellent local cycling infrastructure. 
                However, strategic road capacity remains constrained, particularly on the A14 corridor.
              </p>
              
               <div className="flex items-center gap-2 pl-4 border-l-2 border-blue-200 py-1">
                   <Link2 className="w-3.5 h-3.5 text-blue-500" />
                   <span className="text-sm font-medium text-blue-700 cursor-pointer hover:underline">Evidence Source: DfT Connectivity Tool</span>
              </div>
              
               <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex gap-3 text-sm text-slate-600">
                 <Info className="w-5 h-5 text-slate-400 flex-shrink-0" />
                 <div>
                    <span className="font-semibold text-slate-700">Methodology Note:</span> DfT Connectivity Tool provides journey time accessibility but does not account for capacity constraints 
                    or local congestion patterns. Supplementary traffic modeling is in progress.
                 </div>
              </div>
            </section>
          </>
        ) : (
          <>
            <section className="space-y-6">
              <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                 <span className="text-slate-300 text-xl font-normal">01</span> Site & Proposal
              </h2>
              <Card className="bg-slate-50/50 border-slate-200 shadow-sm">
                 <CardContent className="p-6">
                    <div className="grid grid-cols-2 gap-y-4 gap-x-8 text-sm">
                       <div>
                            <div className="text-slate-500 mb-1">Address</div>
                            <div className="font-medium text-slate-900">45 Mill Road, Cambridge CB1 2AD</div>
                       </div>
                       <div>
                            <div className="text-slate-500 mb-1">Ward</div>
                            <div className="font-medium text-slate-900">Petersfield</div>
                       </div>
                       <div>
                            <div className="text-slate-500 mb-1">Applicant</div>
                            <div className="font-medium text-slate-900">Mill Road Developments Ltd</div>
                       </div>
                       <div>
                            <div className="text-slate-500 mb-1">Agent</div>
                            <div className="font-medium text-slate-900">Smith Planning Associates</div>
                       </div>
                    </div>
                 </CardContent>
              </Card>
              <p>
                The application site comprises a ground floor retail unit (Use Class E) within a two-storey building in the 
                Mill Road District Centre. The proposal seeks to change the use to residential (2 x 1-bed flats), with internal 
                alterations but no external changes.
              </p>
            </section>

            <section className="space-y-4">
              <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2 mt-8">
                  <span className="text-slate-300 text-xl font-normal">02</span> Planning Assessment
              </h2>
              
              <div className="space-y-2">
                <h3 className="text-lg font-semibold text-slate-800">Principle of Development</h3>
                <p>
                    Policy DM12 requires the retention of ground floor retail uses in District Centres unless the unit has been 
                    actively marketed for 12 months. The applicant has provided marketing evidence demonstrating unsuccessful 
                    attempts to let the unit over 15 months at market rates.
                </p>
                
                 <div className="flex items-center gap-2 pl-4 border-l-2 border-purple-200 py-1 mb-4">
                    <Link2 className="w-3.5 h-3.5 text-purple-500" />
                    <span className="text-sm font-medium text-purple-700 cursor-pointer hover:underline">Policy Reference: DM12 (District Centres)</span>
                </div>

                <Alert className="bg-indigo-50 border-indigo-100 text-indigo-900">
                    <MessageSquare className="h-4 w-4 text-indigo-600" />
                    <AlertTitle className="text-indigo-800 font-semibold mb-1">Officer Note</AlertTitle>
                    <AlertDescription className="text-indigo-800/80 text-sm">
                        Highways response received 29 Nov - no objection subject to secure cycle storage condition. 
                        Conservation officer satisfied with internal conversion approach.
                    </AlertDescription>
                </Alert>
              </div>

              <div className="space-y-2 mt-6">
                <h3 className="text-lg font-semibold text-slate-800">Residential Amenity</h3>
                <p>
                    The proposed flats would achieve minimum space standards (Policy H9) and benefit from existing rear courtyard 
                    access. Natural light to habitable rooms is adequate based on site inspection.
                </p>
                
                 <div className="flex items-center gap-2 pl-4 border-l-2 border-blue-200 py-1">
                    <Link2 className="w-3.5 h-3.5 text-blue-500" />
                    <span className="text-sm font-medium text-blue-700 cursor-pointer hover:underline">Evidence Source: Site Visit 12 Dec</span>
                </div>
              </div>
            </section>

            <section className="space-y-6">
              <h2 className="text-2xl font-bold text-slate-900 flex items-center gap-2 mt-8">
                  <span className="text-slate-300 text-xl font-normal">03</span> Recommendation
              </h2>
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                    <div className="h-8 w-8 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600">
                        <CheckCircle className="w-5 h-5" />
                    </div>
                    <span className="text-lg font-bold text-emerald-800 tracking-wide">APPROVE</span>
                </div>
                <p className="text-sm text-emerald-900/80 font-medium">
                  Subject to conditions:
                </p>
                <ul className="list-disc pl-5 mt-2 space-y-1 text-sm text-emerald-900/70">
                    <li>Secure cycle storage (2 spaces)</li>
                    <li>Removal of permitted development rights</li>
                    <li>Retention of front elevation details</li>
                </ul>
              </div>
            </section>
          </>
        )}
      </div>

      {/* Floating Toolbar */}
      <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-30">
        <div className="bg-white/90 backdrop-blur-md rounded-full shadow-xl border border-slate-200 p-1.5 flex items-center gap-1.5 ring-1 ring-black/5">
          <TooltipButton icon={Link2} label="Insert Citation" />
          <TooltipButton icon={MessageSquare} label="Add Comment" />
          <TooltipButton icon={Plus} label="Insert Evidence" />
          <div className="w-px h-5 bg-slate-200 mx-1" />
          <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white rounded-full px-4 h-9 shadow-sm gap-2">
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI Suggestion</span>
          </Button>
        </div>
      </div>
    </div>
  );
}

function TooltipButton({ icon: Icon, label }: { icon: any, label: string }) {
    return (
        <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full text-slate-500 hover:text-slate-900 hover:bg-slate-100" title={label}>
            <Icon className="w-4 h-4" />
        </Button>
    )
}
