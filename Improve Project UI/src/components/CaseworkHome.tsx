import { LayoutGrid, AlertTriangle, CheckCircle, Clock, FileText, ArrowRight, Search, Filter, MoreHorizontal, Calendar, MapPin } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Logo } from "./Logo";

interface CaseworkHomeProps {
  onOpenCase: (caseId: string) => void;
  onSwitchWorkspace: () => void;
}

interface CaseItem {
  id: string;
  reference: string;
  address: string;
  description: string;
  status: 'new' | 'validating' | 'consultation' | 'assessment' | 'determination' | 'issued';
  daysRemaining: number;
  officer: string;
  receivedDate: string;
}

const mockCases: CaseItem[] = [
  {
    id: '1',
    reference: '24/0456/FUL',
    address: '45 Mill Road, Cambridge',
    description: 'Change of use from retail to residential (2 flats)',
    status: 'assessment',
    daysRemaining: 12,
    officer: 'Sarah Mitchell',
    receivedDate: '15 Oct 2024'
  },
  {
    id: '2',
    reference: '24/0523/FUL',
    address: 'Land at Cherry Hinton Road',
    description: 'Residential development of 24 dwellings with associated access and landscaping',
    status: 'consultation',
    daysRemaining: 28,
    officer: 'James Chen',
    receivedDate: '28 Oct 2024'
  },
  {
    id: '3',
    reference: '24/0489/FUL',
    address: '12 Station Road, Trumpington',
    description: 'Single storey rear extension to provide additional living space',
    status: 'determination',
    daysRemaining: 3,
    officer: 'Sarah Mitchell',
    receivedDate: '20 Oct 2024'
  },
  {
    id: '4',
    reference: '24/0601/FUL',
    address: 'Cambridge Science Park, Unit 7',
    description: 'Extension to existing commercial building',
    status: 'new',
    daysRemaining: 56,
    officer: 'Unassigned',
    receivedDate: '10 Nov 2024'
  },
];

const statusConfig = {
  new: { label: 'New', className: 'bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200' },
  validating: { label: 'Validating', className: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100' },
  consultation: { label: 'Consultation', className: 'bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100' },
  assessment: { label: 'Assessment', className: 'bg-orange-50 text-orange-700 border-orange-200 hover:bg-orange-100' },
  determination: { label: 'Determination', className: 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100' },
  issued: { label: 'Issued', className: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100' },
};

export function CaseworkHome({ onOpenCase, onSwitchWorkspace }: CaseworkHomeProps) {
  const urgentCases = mockCases.filter(c => c.daysRemaining < 7);

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--color-surface)' }}>
      {/* Header */}
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
        {/* Stats Banner */}
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
                    <div className="text-3xl font-bold mb-1" style={{ color: 'var(--color-ink)' }}>24</div>
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
                    <div className="text-3xl font-bold mb-1" style={{ color: 'var(--color-ink)' }}>8</div>
                    <p className="text-sm" style={{ color: 'var(--color-text)' }}>In Consultation</p>
                </div>
            </CardContent>
          </Card>

          <Card className="border-red-100 bg-red-50/30 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden">
            <div className="absolute top-0 right-0 p-2 opacity-10">
                <AlertTriangle className="w-24 h-24 text-red-500" />
            </div>
            <CardContent className="p-6 relative z-10">
                <div className="flex items-center justify-between mb-4">
                    <div className="bg-red-100 p-2 rounded-lg">
                        <AlertTriangle className="w-5 h-5 text-red-600" />
                    </div>
                    <Badge className="bg-red-100 text-red-700 hover:bg-red-100 border-0">Action Required</Badge>
                </div>
                <div>
                    <div className="text-3xl font-bold text-red-700 mb-1">{urgentCases.length}</div>
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
                    <Badge variant="outline" className="text-xs font-normal text-emerald-600 bg-emerald-50 border-emerald-100">+2 from last week</Badge>
                </div>
                <div>
                    <div className="text-3xl font-bold mb-1" style={{ color: 'var(--color-ink)' }}>15</div>
                    <p className="text-sm" style={{ color: 'var(--color-text)' }}>Determined This Month</p>
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
                        <CardDescription>Manage applications through validation, consultation, and determination</CardDescription>
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
            <CardContent className="p-0">
                <div className="divide-y" style={{ borderColor: 'var(--color-neutral-200)' }}>
                    {mockCases.map((caseItem) => (
                        <div 
                            key={caseItem.id} 
                            className="group p-5 hover:bg-white/50 transition-all cursor-pointer flex flex-col sm:flex-row gap-4 sm:items-center"
                            onClick={() => onOpenCase(caseItem.id)}
                        >
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-3 mb-2">
                                    <span className="font-mono text-sm font-medium px-2 py-0.5 rounded" style={{
                                      color: 'var(--color-ink)',
                                      backgroundColor: 'var(--color-surface)'
                                    }}>
                                        {caseItem.reference}
                                    </span>
                                    <Badge variant="outline" className={`font-normal ${statusConfig[caseItem.status].className}`}>
                                        {statusConfig[caseItem.status].label}
                                    </Badge>
                                    {caseItem.daysRemaining < 7 && (
                                        <Badge variant="destructive" className="font-normal text-xs flex items-center gap-1">
                                            <Clock className="w-3 h-3" />
                                            {caseItem.daysRemaining} days left
                                        </Badge>
                                    )}
                                </div>
                                
                                <h3 className="text-base font-semibold mb-1 transition-colors" style={{ 
                                  color: 'var(--color-ink)'
                                }}>
                                    {caseItem.address}
                                </h3>
                                <p className="text-sm line-clamp-1 mb-3" style={{ color: 'var(--color-text)' }}>
                                    {caseItem.description}
                                </p>

                                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs" style={{ color: 'var(--color-text)' }}>
                                    <div className="flex items-center gap-1.5">
                                        <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold" style={{
                                          backgroundColor: 'var(--color-neutral-300)',
                                          color: 'var(--color-text)'
                                        }}>
                                            {caseItem.officer.split(' ').map(n => n[0]).join('')}
                                        </div>
                                        <span>{caseItem.officer}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <Calendar className="w-3.5 h-3.5" style={{ color: 'var(--color-text-light)' }} />
                                        <span>Received {caseItem.receivedDate}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <Clock className="w-3.5 h-3.5" style={{ color: 'var(--color-text-light)' }} />
                                        <span>Target: {caseItem.daysRemaining} days</span>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                                <Button size="sm" variant="secondary" className="bg-white border shadow-sm hover:bg-white/80" style={{ borderColor: 'var(--color-neutral-300)' }}>
                                    Quick View
                                </Button>
                                <Button size="sm" style={{
                                  backgroundColor: 'var(--color-accent)',
                                  color: 'white'
                                }}>
                                    Open Case
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            </CardContent>
            <CardFooter className="border-t p-4 flex justify-center" style={{ 
              backgroundColor: 'var(--color-surface-light)',
              borderColor: 'var(--color-neutral-200)'
            }}>
                <Button variant="ghost" size="sm" style={{ color: 'var(--color-text)' }}>
                    Load More Cases
                </Button>
            </CardFooter>
        </Card>
      </div>
    </div>
  );
}