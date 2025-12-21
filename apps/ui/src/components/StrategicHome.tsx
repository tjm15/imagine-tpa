import { useRef } from 'react';
import { LayoutGrid, Calendar, AlertCircle, CheckCircle, Clock, ArrowRight, ChevronRight, MapPin, Building2, Plus, FileText } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Progress } from "./ui/progress";
import { Logo } from "./Logo";
import { useProject } from '../contexts/AuthorityContext';

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

// "Fresh" state stages - all not started
const defaultStages: StageStatus[] = [
  { stage: 'Notice & Boundary', status: 'not-started', dueDate: 'Month 1', description: 'Initial public notice and boundary definition.' },
  { stage: 'Timetable Published', status: 'not-started', dueDate: 'Month 2', description: 'Local Development Scheme updated.' },
  { stage: 'Scoffing & Evidence', status: 'not-started', dueDate: 'Month 3', description: 'Initial scoping and evidence gathering.' },
  { stage: 'Baseline & Place Portrait', status: 'not-started', dueDate: 'Month 6', description: 'Establishing the current state of the area.' },
  { stage: 'Vision & Outcomes', status: 'not-started', dueDate: 'Month 7', description: 'Defining strategic objectives.' },
  { stage: 'Sites Stage 1: Identify', status: 'not-started', dueDate: 'Month 9', description: 'Call for sites and initial filtering.' },
  { stage: 'Sites Stage 2: Assess', status: 'not-started', dueDate: 'Month 12', description: 'Detailed site assessment and selection.' },
  { stage: 'Regulation 18', status: 'not-started', dueDate: 'Month 14', description: 'Draft plan consultation.' },
];

export function StrategicHome({ onOpenProject, onSwitchWorkspace }: StrategicHomeProps) {
  const { authority, setAuthority, authorities, loadingAuthorities } = useProject();

  // 1. Empty/Onboarding View (No Authority Selected)
  if (!authority) {
    return (
      <div className="min-h-screen flex flex-col" style={{ backgroundColor: 'var(--color-surface)' }}>
        <header className="bg-white border-b sticky top-0 z-10" style={{ borderColor: 'var(--color-neutral-300)' }}>
          <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Logo className="w-10 h-9" />
              <div>
                <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>The Planner's Assistant</h1>
                <p className="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>Strategic Planning Workspace</p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <div className="max-w-md w-full space-y-8">
            <div className="p-8 bg-white rounded-2xl shadow-lg border" style={{ borderColor: 'var(--color-edge)' }}>
              <div className="w-16 h-16 rounded-full bg-blue-50 flex items-center justify-center mx-auto mb-6">
                <Building2 className="w-8 h-8 text-blue-600" />
              </div>
              <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--color-ink)' }}>Select Local Authority</h2>
              <p className="text-sm text-slate-500 mb-8">
                Choose a planning authority to begin working on the Local Plan or modify an existing feedback session.
              </p>

              <div className="space-y-4">
                <div className="grid gap-2 text-left">
                  <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">Authority</label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    onChange={(e) => {
                      const auth = authorities.find(a => a.id === e.target.value);
                      if (auth) setAuthority(auth);
                    }}
                    value=""
                    disabled={loadingAuthorities}
                  >
                    <option value="" disabled>Select an authority...</option>
                    {authorities.map(auth => (
                      <option key={auth.id} value={auth.id}>{auth.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // 2. Active Dashboard (Fresh State)
  const completedStages = 0; // Fresh state
  const progress = 0;

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--color-surface)' }}>
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-10" style={{ borderColor: 'var(--color-neutral-300)' }}>
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Logo className="w-10 h-9" />
            <div>
              <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>The Planner's Assistant</h1>
              <div className="flex items-center gap-2">
                <p className="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>Strategic Planning Workspace</p>
                <span className="text-xs text-slate-300">/</span>
                <p className="text-xs font-medium text-slate-600">{authority.name}</p>
                <button onClick={() => setAuthority(null)} className="text-[10px] text-blue-600 hover:underline">Change</button>
              </div>
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
                  Ready to Initiate
                </div>
                <h2 className="text-3xl font-bold tracking-tight mb-3">Welcome to {authority.name} Plan</h2>
                <p className="text-blue-100/90 text-lg leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.85)' }}>
                  Begin your 30-month journey through evidence gathering, scenario planning, and gateway assessments.
                  {/* You are currently in the <span className="font-semibold text-white">Baseline Stage</span>. */}
                </p>
              </div>
              <Button
                onClick={() => onOpenProject('new-plan')}
                size="lg"
                className="shadow-lg border-0 font-medium"
                style={{
                  backgroundColor: 'var(--color-brand)',
                  color: 'var(--color-ink)'
                }}
              >
                Start New Plan <ChevronRight className="ml-2 w-4 h-4" />
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
                    <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>0% Complete</span>
                    <Progress value={progress} className="w-24 h-2" />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y" style={{ borderColor: 'var(--color-neutral-200)' }}>
                  {defaultStages.map((stage, idx) => (
                    <div key={idx} className="group flex items-start gap-4 p-5 hover:bg-white/50 transition-colors cursor-default">
                      <div className="flex flex-col items-center gap-2 pt-1">
                        {/* Status Icons */}
                        <div className="h-6 w-6 rounded-full border ring-4 ring-white" style={{
                          backgroundColor: 'var(--color-surface)',
                          borderColor: 'var(--color-neutral-300)'
                        }} />

                        {idx !== defaultStages.length - 1 && (
                          <div className="w-px h-full group-hover:bg-opacity-50 transition-colors min-h-[2rem]" style={{
                            backgroundColor: 'var(--color-neutral-300)'
                          }} />
                        )}
                      </div>

                      <div className="flex-1 min-w-0 pt-0.5">
                        <div className="flex items-center justify-between gap-4 mb-1">
                          <h4 className={`text-sm font-semibold`} style={{
                            color: 'var(--color-text-light)'
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
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <Card className="border shadow-sm overflow-hidden" style={{ borderColor: 'var(--color-neutral-300)' }}>
              <div className="h-1.5 w-full" style={{ backgroundColor: 'var(--color-accent)' }} />
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>Current Focus</CardTitle>
                <CardDescription>No active stage</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center py-6 text-slate-500 text-sm">
                  <Clock className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                  <p>Timeline not started.</p>
                  <p className="text-xs mt-1">Initialize the plan to see deliverables.</p>
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
                    <span>Upload GIS boundary for {authority.name}</span>
                  </li>
                  <li className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--color-text-dark)' }}>
                    <div className="h-1.5 w-1.5 rounded-full mt-2 flex-shrink-0" style={{ backgroundColor: 'var(--color-accent)' }} />
                    <span>Confirm Local Development Scheme</span>
                  </li>
                  <li className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--color-text-dark)' }}>
                    <div className="h-1.5 w-1.5 rounded-full mt-2 flex-shrink-0" style={{ backgroundColor: 'var(--color-accent)' }} />
                    <span>Invite team members</span>
                  </li>
                </ul>
              </CardContent>
              <CardFooter>
                <Button variant="link" className="p-0 h-auto text-sm" style={{ color: 'var(--color-accent)' }}>Prepare Workspace &rarr;</Button>
              </CardFooter>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
