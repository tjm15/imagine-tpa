import React from 'react';
import { Info } from 'lucide-react';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "./ui/tooltip";

interface InlineHintProps {
    text: str;
    sourceType: 'policy' | 'data' | 'inference';
    summary: str;
}

const InlineHint: React.FC<InlineHintProps> = ({ text, sourceType, summary }) => {
    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <span className="cursor-help decoration-stone-400 decoration-dotted underline underline-offset-2 hover:bg-yellow-50/50 transition-colors">
                        {text}
                        <Info className="inline-block w-3 h-3 ml-1 text-stone-400 mb-0.5" />
                    </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs bg-white border-stone-200 shadow-lg text-stone-800 p-3">
                    <p className="font-semibold text-xs uppercase tracking-wider text-stone-500 mb-1">{sourceType}</p>
                    <p className="text-sm">{summary}</p>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
};

export default InlineHint;
