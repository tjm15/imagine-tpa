import { useEffect, useState } from 'react';
import {
    BookOpen, FileText, MapPin, Shield, Database,
    TrendingUp, AlertTriangle, ExternalLink, Plus
} from 'lucide-react';
import { WorkspaceMode } from '../App';
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import { useProject } from "../contexts/AuthorityContext";

interface ContextMarginProps {
    workspace: WorkspaceMode;
}

interface AdviceCard {
    instance_id: string;
    card_id: string;
    card_title: string | null;
    card_type: string | null;
    basis: string | null;
    priority: string | null;
    status: string | null;
    prompt: string | null;
    document_title: string | null;
    document_status: string | null;
}

export function ContextMargin({ workspace }: ContextMarginProps) {
    const { authority, planProject } = useProject();
    const [adviceCards, setAdviceCards] = useState<AdviceCard[]>([]);
    const [adviceLoading, setAdviceLoading] = useState(false);
    const [adviceError, setAdviceError] = useState<string | null>(null);

    useEffect(() => {
        if (workspace !== 'plan') return;
        if (!planProject?.plan_project_id) return;
        const controller = new AbortController();
        const loadAdvice = async () => {
            setAdviceLoading(true);
            setAdviceError(null);
            try {
                const resp = await fetch(`/api/advice-cards?plan_project_id=${planProject.plan_project_id}&limit=12`, {
                    signal: controller.signal,
                });
                if (!resp.ok) {
                    throw new Error(`Advice cards unavailable (${resp.status})`);
                }
                const data = await resp.json();
                const cards = Array.isArray(data.advice_cards) ? data.advice_cards : [];
                setAdviceCards(cards);
            } catch (err: any) {
                if (err?.name !== 'AbortError') {
                    setAdviceError(err?.message || 'Failed to load advice cards');
                }
            } finally {
                setAdviceLoading(false);
            }
        };
        loadAdvice();
        return () => controller.abort();
    }, [workspace, planProject?.plan_project_id]);

    const priorityStyles: Record<string, string> = {
        Critical: 'bg-rose-50 text-rose-700 border-rose-200',
        Important: 'bg-amber-50 text-amber-800 border-amber-200',
        Helpful: 'bg-slate-100 text-slate-600 border-slate-200',
    };

    return (
        <div className="h-full flex flex-col bg-slate-50/50">
            <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Context & Evidence</h3>
                <Button variant="ghost" size="icon" className="h-6 w-6">
                    <Plus className="w-4 h-4 text-slate-500" />
                </Button>
            </div>

            <ScrollArea className="flex-1">
                <div className="p-4 space-y-4">

                    {/* Smart Feed */}
                    <Card className="border-blue-100 shadow-sm bg-blue-50/30 overflow-hidden">
                        <CardHeader className="p-3 pb-2 flex flex-row items-center gap-2 space-y-0">
                            <TrendingUp className="w-4 h-4 text-blue-600" />
                            <CardTitle className="text-xs font-semibold text-blue-900 uppercase tracking-wider">Smart Suggestions</CardTitle>
                        </CardHeader>
                        <CardContent className="p-3 pt-0">
                            <div className="bg-white p-3 rounded-md border border-blue-100 shadow-sm">
                                <p className="text-xs text-slate-600 mb-2 leading-relaxed">
                                    Transport baseline data available from <span className="font-medium text-slate-900">DfT Connectivity Tool</span>.
                                </p>
                                <Button size="sm" variant="secondary" className="w-full h-7 text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200">
                                    Insert as Evidence
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Advice Cards */}
                    {workspace === 'plan' && (
                        <>
                            <div className="space-y-2">
                                <div className="flex items-center justify-between px-1">
                                    <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Advice Cards</h4>
                                    <span className="text-[10px] text-slate-400">{adviceCards.length} active</span>
                                </div>
                                {adviceLoading && (
                                    <p className="text-xs text-slate-500 px-1">Loading advisory prompts…</p>
                                )}
                                {adviceError && (
                                    <p className="text-xs text-amber-700 px-1">{adviceError}</p>
                                )}
                                {!adviceLoading && !adviceError && adviceCards.length === 0 && (
                                    <p className="text-xs text-slate-400 px-1">No advice cards matched yet.</p>
                                )}
                                <div className="space-y-2">
                                    {adviceCards.slice(0, 4).map((card) => (
                                        <Card key={card.instance_id} className="border-slate-200 shadow-sm">
                                            <CardContent className="p-3 space-y-2">
                                                <div className="flex items-start justify-between gap-2">
                                                    <div>
                                                        <p className="text-xs font-semibold text-slate-800">
                                                            {card.card_title || 'Advice prompt'}
                                                        </p>
                                                        {card.document_title && (
                                                            <p className="text-[10px] text-slate-500 mt-1">
                                                                {card.document_title}
                                                            </p>
                                                        )}
                                                    </div>
                                                    {card.priority && (
                                                        <Badge
                                                            variant="outline"
                                                            className={`text-[9px] h-4 px-1 ${priorityStyles[card.priority] || 'text-slate-500 border-slate-200'}`}
                                                        >
                                                            {card.priority}
                                                        </Badge>
                                                    )}
                                                </div>
                                                {card.prompt && (
                                                    <p className="text-[11px] text-slate-600 leading-relaxed">{card.prompt}</p>
                                                )}
                                                <div className="flex items-center flex-wrap gap-1.5 text-[9px] text-slate-500">
                                                    {card.card_type && (
                                                        <Badge variant="secondary" className="h-4 px-1 bg-white border border-slate-200 text-slate-500">
                                                            {card.card_type}
                                                        </Badge>
                                                    )}
                                                    {card.basis && (
                                                        <Badge variant="secondary" className="h-4 px-1 bg-white border border-slate-200 text-slate-500">
                                                            {card.basis}
                                                        </Badge>
                                                    )}
                                                </div>
                                                <p className="text-[10px] text-slate-400">{card.status || 'Advisory only — planner judgement required'}</p>
                                            </CardContent>
                                        </Card>
                                    ))}
                                </div>
                            </div>

                            <Separator />
                        </>
                    )}

                    {/* Live Policy Surface */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between px-1">
                            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Relevant Policies</h4>
                            <Button variant="link" className="text-[10px] h-auto p-0 text-blue-600">View All</Button>
                        </div>

                        <div className="space-y-2">
                            {[
                                { ref: 'LP/2024/S1', title: 'Spatial Strategy', relevance: 'high' },
                                { ref: 'LP/2024/H1', title: 'Housing Delivery', relevance: 'high' },
                                { ref: 'LP/2024/T2', title: 'Sustainable Transport', relevance: 'medium' },
                                { ref: 'LP/2024/ENV3', title: 'Green Infrastructure', relevance: 'medium' },
                            ].map((policy) => (
                                <Card key={policy.ref} className="group cursor-pointer hover:border-blue-300 transition-colors shadow-sm">
                                    <CardContent className="p-2.5 flex items-start justify-between gap-2">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-1">
                                                <Badge variant="outline" className="font-mono text-[10px] bg-slate-50 text-slate-600 border-slate-200 group-hover:border-blue-200 group-hover:text-blue-700">
                                                    {policy.ref}
                                                </Badge>
                                                {policy.relevance === 'high' && (
                                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" title="High Relevance" />
                                                )}
                                            </div>
                                            <p className="text-xs font-medium text-slate-700 group-hover:text-slate-900 truncate">
                                                {policy.title}
                                            </p>
                                        </div>
                                        <ExternalLink className="w-3 h-3 text-slate-300 group-hover:text-blue-500 transition-colors mt-1" />
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>

                    <Separator />

                    {/* Evidence Shelf */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between px-1">
                            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Evidence Shelf</h4>
                        </div>

                        <div className="space-y-2">
                            <Card className="group cursor-move border-dashed border-slate-300 hover:border-blue-400 hover:bg-blue-50/50 transition-all shadow-none bg-slate-50/50">
                                <CardContent className="p-2.5">
                                    <div className="flex items-start gap-2 mb-1.5">
                                        <FileText className="w-4 h-4 text-slate-400 group-hover:text-blue-500 mt-0.5" />
                                        <div>
                                            <p className="text-xs font-medium text-slate-700 group-hover:text-slate-900">Census 2021: Housing Stock</p>
                                            <p className="text-[10px] text-slate-500">ONS Census data for {authority?.name || 'Area'}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1.5 mt-2">
                                        <Badge variant="secondary" className="h-4 text-[9px] px-1 bg-white border border-slate-200 text-slate-500">
                                            <Shield className="w-2.5 h-2.5 mr-1" /> ONS Open Data
                                        </Badge>
                                    </div>
                                </CardContent>
                            </Card>

                            <Card className="group cursor-move border-dashed border-slate-300 hover:border-blue-400 hover:bg-blue-50/50 transition-all shadow-none bg-slate-50/50">
                                <CardContent className="p-2.5">
                                    <div className="flex items-start gap-2 mb-1.5">
                                        <MapPin className="w-4 h-4 text-slate-400 group-hover:text-blue-500 mt-0.5" />
                                        <div>
                                            <p className="text-xs font-medium text-slate-700 group-hover:text-slate-900">Constraints Map</p>
                                            <p className="text-[10px] text-slate-500">Green Belt, Flood Zones</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1.5 mt-2">
                                        <Badge variant="secondary" className="h-4 text-[9px] px-1 bg-white border border-slate-200 text-slate-500">
                                            <Shield className="w-2.5 h-2.5 mr-1" /> Internal GIS
                                        </Badge>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        <p className="text-[10px] text-slate-400 flex items-center gap-1.5 px-1 pt-1">
                            <AlertTriangle className="w-3 h-3" />
                            Drag cards into document to cite
                        </p>
                    </div>

                    <Separator />

                    {/* Mini Preview */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between px-1">
                            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Site Context</h4>
                        </div>
                        <div className="aspect-video bg-slate-100 rounded-md border border-slate-200 relative overflow-hidden group cursor-pointer">
                            <div className="absolute inset-0 flex items-center justify-center text-slate-400 group-hover:text-slate-500 bg-slate-100 group-hover:bg-slate-200 transition-colors">
                                <MapPin className="w-6 h-6" />
                            </div>
                            <div className="absolute bottom-0 left-0 right-0 bg-black/60 p-1.5 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity">
                                <p className="text-[10px] text-white font-medium truncate">{authority?.name || 'Local'} Urban Area</p>
                            </div>
                        </div>
                    </div>

                </div>
            </ScrollArea>
        </div>
    );
}
