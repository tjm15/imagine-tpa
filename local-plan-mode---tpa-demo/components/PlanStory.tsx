import React from 'react';
import { Scenario } from '../types';
import { Quote } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface PlanStoryProps {
  scenario: Scenario;
}

const PlanStory: React.FC<PlanStoryProps> = ({ scenario }) => {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col">
      <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
        <span className="w-1 h-6 bg-indigo-500 rounded-full block"></span>
        Plan Narrative
      </h2>
      
      <div className="relative">
        <Quote className="absolute -top-2 -left-2 text-indigo-100 w-10 h-10 -z-10" />
        <div className="prose prose-sm text-slate-600 leading-relaxed max-h-[60vh] overflow-y-auto pr-2">
          <ReactMarkdown
             components={{
                p: ({node, ...props}) => <p className="mb-3" {...props} />,
                strong: ({node, ...props}) => <strong className="font-semibold text-slate-800" {...props} />,
                ul: ({node, ...props}) => <ul className="list-disc ml-4 mb-3" {...props} />,
                li: ({node, ...props}) => <li className="mb-1" {...props} />
             }}
          >
            {scenario.narrative}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
};

export default PlanStory;