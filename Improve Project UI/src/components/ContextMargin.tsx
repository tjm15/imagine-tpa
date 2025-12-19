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

interface ContextMarginProps {
  workspace: WorkspaceMode;
}

export function ContextMargin({ workspace }: ContextMarginProps) {
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
                                    <p className="text-[10px] text-slate-500">ONS Census data for Cambridge</p>
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
                         <p className="text-[10px] text-white font-medium truncate">Cambridge Urban Area</p>
                    </div>
                </div>
            </div>

        </div>
      </ScrollArea>
    </div>
  );
}
