import { LayoutGrid, AlertTriangle, CheckCircle, Clock, FileText, ArrowRight, Search, Filter, MoreHorizontal, Calendar, MapPin, Inbox, Building2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Logo } from "./Logo";
import { useProject, AVAILABLE_AUTHORITIES } from '../contexts/AuthorityContext';

interface CaseworkHomeProps {
  onOpenCase: (caseId: string) => void;
  onSwitchWorkspace: () => void;
}

export function CaseworkHome({ onOpenCase, onSwitchWorkspace }: CaseworkHomeProps) {
  const { authority, setAuthority } = useProject();

  if (!authority) {
    return (
      <div className="min-h-screen flex flex-col" style={{ backgroundColor: 'var(--color-surface)' }}>
        <header className="bg-white border-b sticky top-0 z-10" style={{ borderColor: 'var(--color-neutral-300)' }}>
          <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Logo className="w-10 h-9" />
              <div>
                <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>The Planner's Assistant</h1>
                <p className="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>Development Management Workspace</p>
              </div>
            </div>
            <Button
              variant="outline"
              onClick={onSwitchWorkspace}
              className="border hover:bg-white/50"
              style={{ color: 'var(--color-text)', borderColor: 'var(--color-neutral-300)' }}
            >
              Switch to Plan Studio <ArrowRight className="ml-2 w-4 h-4" />
            </Button>
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
                Choose a planning authority to view active casework.
              </p>

              <div className="space-y-4">
                <div className="grid gap-2 text-left">
                  <label className="text-xs font-semibold uppercase tracking-wider text-slate-500">Authority</label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    onChange={(e) => {
                      const auth = AVAILABLE_AUTHORITIES.find(a => a.id === e.target.value);
                      if (auth) setAuthority(auth);
                    }}
                    value=""
                  >
                    <option value="" disabled>Select an authority...</option>
                    {AVAILABLE_AUTHORITIES.map(auth => (
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

  // Fresh state - no cases
  const activeCasesCount = 0;
  const inConsultationCount = 0;
  const urgentCount = 0;
  const determinedCount = 0;

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
                <p className="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>Development Management Workspace</p>
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
            Switch to Plan Studio <ArrowRight className="ml-2 w-4 h-4" />
          </Button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-10">
        {/* Stats Banner (Empty State) */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <Card className="border shadow-sm hover:shadow-md transition-shadow" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="p-2 rounded-lg" style={{ backgroundColor: 'rgba(50, 156, 133, 0.1)' }}>
                  <FileText className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
                </div>
                <Badge variant="outline" className="text-xs font-normal border" style={{
                  color: 'var(--color-text)',
                  borderColor: 'var(--color-neutral-300)'
                }}>Total</Badge>
              </div>
              <div>
                <div className="text-3xl font-bold mb-1" style={{ color: 'var(--color-ink)' }}>{activeCasesCount}</div>
                <p className="text-sm" style={{ color: 'var(--color-text)' }}>Active Cases</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border shadow-sm hover:shadow-md transition-shadow" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="bg-purple-50 p-2 rounded-lg">
                  <Clock className="w-5 h-5 text-purple-600" />
                </div>
                <Badge variant="outline" className="text-xs font-normal text-purple-600 bg-purple-50 border-purple-100">Active</Badge>
              </div>
              <div>
                <div className="text-3xl font-bold mb-1" style={{ color: 'var(--color-ink)' }}>{inConsultationCount}</div>
                <p className="text-sm" style={{ color: 'var(--color-text)' }}>In Consultation</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-red-50 bg-red-50/10 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardContent className="p-6 relative z-10">
              <div className="flex items-center justify-between mb-4">
                <div className="bg-red-50 p-2 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-red-600" />
                </div>
                <Badge className="bg-red-50 text-red-700 hover:bg-red-50 border-0">Attention</Badge>
              </div>
              <div>
                <div className="text-3xl font-bold text-red-700 mb-1">{urgentCount}</div>
                <p className="text-sm text-red-600 font-medium">Urgent (≤7 days)</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border shadow-sm hover:shadow-md transition-shadow" style={{ borderColor: 'var(--color-neutral-300)' }}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="bg-emerald-50 p-2 rounded-lg">
                  <CheckCircle className="w-5 h-5 text-emerald-600" />
                </div>
                <Badge variant="outline" className="text-xs font-normal text-emerald-600 bg-emerald-50 border-emerald-100">Monthly</Badge>
              </div>
              <div>
                <div className="text-3xl font-bold mb-1" style={{ color: 'var(--color-ink)' }}>{determinedCount}</div>
                <p className="text-sm" style={{ color: 'var(--color-text)' }}>Determined</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Content */}
        <Card className="border shadow-sm" style={{ borderColor: 'var(--color-neutral-300)' }}>
          <CardHeader className="border-b" style={{
            borderColor: 'var(--color-neutral-200)',
            backgroundColor: 'var(--color-surface-light)'
          }}>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <CardTitle className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>Case Inbox</CardTitle>
                <CardDescription>Manage applications for {authority.name}</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4" style={{ color: 'var(--color-text-light)' }} />
                  <Input placeholder="Search cases..." className="pl-9 w-[250px] bg-white" />
                </div>
                <Button variant="outline" size="icon" style={{ color: 'var(--color-text)' }}>
                  <Filter className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0 min-h-[400px] flex flex-col items-center justify-center text-center">
            {/* Empty State for Table */}
            <div className="max-w-sm mx-auto p-6">
              <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
                <Inbox className="w-8 h-8 text-slate-400" />
              </div>
              <h3 className="text-lg font-medium text-slate-900 mb-1">No Active Cases</h3>
              <p className="text-sm text-slate-500 mb-6">There are no planning applications currently assigned to this view. Import a new case to get started.</p>
              <Button
                onClick={() => onOpenCase('new')}
                style={{
                  backgroundColor: 'var(--color-accent)',
                  color: 'white'
                }}
              >
                Import Application
              </Button>
            </div>
          </CardContent>
          <CardFooter className="border-t p-4 flex justify-center" style={{
            backgroundColor: 'var(--color-surface-light)',
            borderColor: 'var(--color-neutral-200)'
          }}>
            <p className="text-xs text-slate-400">Syncing with planning register...</p>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}