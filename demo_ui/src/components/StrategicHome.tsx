import { LayoutGrid, Calendar, AlertCircle, CheckCircle, Clock, ArrowRight, ChevronRight, MapPin } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Progress } from "./ui/progress";
import { Logo } from "./Logo";

interface StrategicHomeProps {
  onOpenProject: (projectId: string) => void;
  onSwitchWorkspace: () => void;
}

interface StageStatus {
  stage: string;
  status: 'complete' | 'in-progress' | 'blocked' | 'not-started';
  dueDate: string;
  blockers?: string[];
  description: string;
}

const mockStages: StageStatus[] = [
  { stage: 'Notice & Boundary', status: 'complete', dueDate: 'Jan 2025', description: 'Initial public notice and boundary definition.' },
  { stage: 'Timetable Published', status: 'complete', dueDate: 'Feb 2025', description: 'Local Development Scheme updated.' },
  { stage: 'Gateway 1', status: 'complete', dueDate: 'Mar 2025', description: 'Initial scoping and evidence gathering.' },
  { stage: 'Baseline & Place Portrait', status: 'in-progress', dueDate: 'Jun 2025', blockers: ['Transport baseline incomplete'], description: 'Establishing the current state of the area.' },
  { stage: 'Vision & Outcomes', status: 'not-started', dueDate: 'Jul 2025', description: 'Defining strategic objectives.' },
  { stage: 'Sites Stage 1: Identify', status: 'not-started', dueDate: 'Sep 2025', description: 'Call for sites and initial filtering.' },
  { stage: 'Sites Stage 2: Assess', status: 'not-started', dueDate: 'Dec 2025', description: 'Detailed site assessment and selection.' },
  { stage: 'Gateway 2', status: 'not-started', dueDate: 'Feb 2026', description: 'Draft plan regulation 18 consultation.' },
];

export function StrategicHome({ onOpenProject, onSwitchWorkspace }: StrategicHomeProps) {
  const completedStages = mockStages.filter(s => s.status === 'complete').length;
  const progress = (completedStages / mockStages.length) * 100;

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--color-surface)' }}>
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-10" style={{ borderColor: 'var(--color-neutral-300)' }}>
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Logo className="w-10 h-9" />
            <div>
              <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>The Planner's Assistant</h1>
              <p className="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>Strategic Planning Workspace</p>
            </div>
          </div>
          <Button 
            variant="outline" 
            onClick={onSwitchWorkspace}
            className="border hover:bg-white/50"
            style={{ 
              color: 'var(--color-text)', 
              borderColor: 'var(--color-neutral-300)'
            }}
          >
            Switch to Casework <ArrowRight className="ml-2 w-4 h-4" />
          </Button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-10">
        {/* Welcome Banner */}
        <section className="mb-10">
            <div className="relative overflow-hidden rounded-2xl text-white shadow-xl" style={{ backgroundColor: 'var(--color-ink)' }}>
                <div className="absolute inset-0 opacity-10" style={{ 
                  background: 'linear-gradient(135deg, var(--color-accent) 0%, var(--color-ink-dark) 100%)'
                }} />
                <div className="relative p-8 md:p-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
                    <div className="max-w-2xl">
                        <div className="inline-flex items-center rounded-full border px-3 py-1 text-sm mb-4 backdrop-blur-sm" style={{
                          borderColor: 'var(--color-brand)',
                          backgroundColor: 'rgba(245, 195, 21, 0.1)',
                          color: 'var(--color-brand-light)'
                        }}>
                            <span className="flex h-2 w-2 rounded-full mr-2 animate-pulse" style={{ backgroundColor: 'var(--color-brand)' }}></span>
                            CULP Programme Active
                        </div>
                        <h2 className="text-3xl font-bold tracking-tight mb-3">Welcome back to Cambridge Local Plan 2025</h2>
                        <p className="text-blue-100/90 text-lg leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.85)' }}>
                            Track your 30-month journey through evidence gathering, scenario planning, and gateway assessments.
                            You are currently in the <span className="font-semibold text-white">Baseline Stage</span>.
                        </p>
                    </div>
                    <Button 
                        onClick={() => onOpenProject('cambridge-2025')}
                        size="lg"
                        className="shadow-lg border-0 font-medium"
                        style={{
                          backgroundColor: 'var(--color-brand)',
                          color: 'var(--color-ink)'
                        }}
                    >
                        Enter Plan Studio <ChevronRight className="ml-2 w-4 h-4" />
                    </Button>
                </div>
            </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Programme Timeline */}
          <div className="lg:col-span-2 space-y-6">
            <Card className="border shadow-sm" style={{ borderColor: 'var(--color-neutral-300)' }}>
              <CardHeader className="border-b pb-4" style={{ 
                borderColor: 'var(--color-neutral-200)',
                backgroundColor: 'var(--color-surface-light)' 
              }}>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Calendar className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
                        <CardTitle className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>Programme Timeline</CardTitle>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>{Math.round(progress)}% Complete</span>
                        <Progress value={progress} className="w-24 h-2" />
                    </div>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y" style={{ borderColor: 'var(--color-neutral-200)' }}>
                  {mockStages.map((stage, idx) => (
                    <div key={idx} className="group flex items-start gap-4 p-5 hover:bg-white/50 transition-colors cursor-default">
                        <div className="flex flex-col items-center gap-2 pt-1">
                            {stage.status === 'complete' && (
                                <div className="h-6 w-6 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 ring-4 ring-white">
                                    <CheckCircle className="w-4 h-4" />
                                </div>
                            )}
                            {stage.status === 'in-progress' && (
                                <div className="h-6 w-6 rounded-full flex items-center justify-center ring-4 ring-white animate-pulse" style={{
                                  backgroundColor: 'rgba(245, 195, 21, 0.2)',
                                  color: 'var(--color-brand)'
                                }}>
                                    <Clock className="w-4 h-4" />
                                </div>
                            )}
                            {stage.status === 'blocked' && (
                                <div className="h-6 w-6 rounded-full bg-red-100 flex items-center justify-center text-red-600 ring-4 ring-white">
                                    <AlertCircle className="w-4 h-4" />
                                </div>
                            )}
                            {stage.status === 'not-started' && (
                                <div className="h-6 w-6 rounded-full border ring-4 ring-white" style={{
                                  backgroundColor: 'var(--color-surface)',
                                  borderColor: 'var(--color-neutral-300)'
                                }} />
                            )}
                            {idx !== mockStages.length - 1 && (
                                <div className="w-px h-full group-hover:bg-opacity-50 transition-colors min-h-[2rem]" style={{
                                  backgroundColor: 'var(--color-neutral-300)'
                                }} />
                            )}
                        </div>
                      
                        <div className="flex-1 min-w-0 pt-0.5">
                            <div className="flex items-center justify-between gap-4 mb-1">
                                <h4 className={`text-sm font-semibold`} style={{ 
                                  color: stage.status === 'not-started' ? 'var(--color-text-light)' : 'var(--color-ink)' 
                                }}>
                                    {stage.stage}
                                </h4>
                                <Badge variant="secondary" className="font-normal text-xs border" style={{
                                  backgroundColor: 'var(--color-surface)',
                                  color: 'var(--color-text)',
                                  borderColor: 'var(--color-neutral-300)'
                                }}>
                                    {stage.dueDate}
                                </Badge>
                            </div>
                            <p className="text-sm" style={{ color: 'var(--color-text)' }}>{stage.description}</p>
                            
                            {stage.blockers && (
                                <div className="flex items-start gap-2 mt-3 p-3 bg-red-50 rounded-md border border-red-100">
                                    <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                                    <p className="text-xs text-red-700 font-medium">{stage.blockers[0]}</p>
                                </div>
                            )}

                            {stage.status === 'in-progress' && (
                                <div className="mt-3 flex gap-2">
                                    <Button size="sm" variant="outline" className="h-8 text-xs">View Requirements</Button>
                                    <Button size="sm" className="h-8 text-xs" style={{
                                      backgroundColor: 'var(--color-accent)',
                                      color: 'white'
                                    }}>Continue Work</Button>
                                </div>
                            )}
                        </div>
                        
                        <div className="pt-0.5">
                            {stage.status === 'complete' && <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 border-0 shadow-none">Complete</Badge>}
                            {stage.status === 'in-progress' && <Badge className="hover:bg-opacity-90 border-0 shadow-none" style={{
                              backgroundColor: 'rgba(245, 195, 21, 0.15)',
                              color: 'var(--color-brand-dark)'
                            }}>In Progress</Badge>}
                            {stage.status === 'blocked' && <Badge className="bg-red-100 text-red-700 hover:bg-red-100 border-0 shadow-none">Blocked</Badge>}
                        </div>
                    </div>
                  ))}
                </div>
              </CardContent>
              <CardFooter className="border-t p-4" style={{ 
                backgroundColor: 'var(--color-surface-light)',
                borderColor: 'var(--color-neutral-200)'
              }}>
                 <Button variant="ghost" size="sm" className="w-full" style={{ color: 'var(--color-text)' }}>
                    View Full Programme Schedule
                 </Button>
              </CardFooter>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <Card className="border shadow-sm overflow-hidden" style={{ borderColor: 'var(--color-neutral-300)' }}>
              <div className="h-1.5 w-full" style={{ backgroundColor: 'var(--color-accent)' }} />
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>Current Focus: Baseline</CardTitle>
                <CardDescription>Key deliverables for this stage</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-start gap-3 p-3 bg-emerald-50/50 rounded-lg border border-emerald-100/50">
                  <div className="bg-emerald-100 p-1.5 rounded-full">
                    <CheckCircle className="w-4 h-4 text-emerald-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-emerald-900">Place Portrait Draft</p>
                    <p className="text-xs text-emerald-700 mt-0.5">Published 15 May</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg border" style={{
                  backgroundColor: 'rgba(245, 195, 21, 0.08)',
                  borderColor: 'rgba(245, 195, 21, 0.2)'
                }}>
                  <div className="p-1.5 rounded-full" style={{ backgroundColor: 'rgba(245, 195, 21, 0.2)' }}>
                    <Clock className="w-4 h-4" style={{ color: 'var(--color-brand-dark)' }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>Transport Baseline</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--color-text)' }}>Work in progress</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg border" style={{
                  backgroundColor: 'var(--color-surface)',
                  borderColor: 'var(--color-neutral-300)'
                }}>
                  <div className="p-1.5 rounded-full" style={{ backgroundColor: 'var(--color-neutral-300)' }}>
                    <div className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>SEA Screening</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-light)' }}>Not started</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border shadow-sm overflow-hidden" style={{ 
              borderColor: 'var(--color-neutral-300)',
              background: `linear-gradient(135deg, ${('var(--color-surface-light)')} 0%, white 100%)`
            }}>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--color-ink)' }}>Next Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  <li className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--color-text-dark)' }}>
                    <div className="h-1.5 w-1.5 rounded-full mt-2 flex-shrink-0" style={{ backgroundColor: 'var(--color-accent)' }} />
                    <span>Commission DfT connectivity analysis</span>
                  </li>
                  <li className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--color-text-dark)' }}>
                    <div className="h-1.5 w-1.5 rounded-full mt-2 flex-shrink-0" style={{ backgroundColor: 'var(--color-accent)' }} />
                    <span>Complete place portrait evidence gaps</span>
                  </li>
                  <li className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--color-text-dark)' }}>
                    <div className="h-1.5 w-1.5 rounded-full mt-2 flex-shrink-0" style={{ backgroundColor: 'var(--color-accent)' }} />
                    <span>Prepare for Gateway 1 self-assessment</span>
                  </li>
                </ul>
              </CardContent>
              <CardFooter>
                 <Button variant="link" className="p-0 h-auto text-sm" style={{ color: 'var(--color-accent)' }}>View Action Log &rarr;</Button>
              </CardFooter>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}