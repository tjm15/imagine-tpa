/**
 * TipTap Document Editor for Planning Documents
 * 
 * Features:
 * - Rich text editing with formatting
 * - Citation marks with evidence linking
 * - Comment threads
 * - AI suggestion insertion
 * - Drag-drop evidence blocks
 * - Track changes mode
 */

import { useCallback, useState, useEffect, useMemo } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Highlight from '@tiptap/extension-highlight';
import { 
  Bold,
  Italic,
  List,
  ListOrdered,
  Quote,
  Heading1,
  Heading2,
  MessageSquare,
  Bookmark,
  Sparkles,
  Undo,
  Redo,
  FileText,
  AlertCircle,
  Loader2,
  HelpCircle,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { useDroppable } from '@dnd-kit/core';
import { useAppState, useAppDispatch } from '../../lib/appState';
import { toast } from 'sonner';
import type { TraceTarget } from '../../lib/trace';

interface DocumentEditorProps {
  initialContent?: string;
  placeholder?: string;
  stageId?: string;
  explainabilityMode?: ExplainabilityMode;
  templateToInsert?: { content: string; id: number } | null;
  onOpenTrace?: (target?: TraceTarget) => void;
  onOpenCoDrafter?: () => void;
  onRequestPatchBundle?: () => void;
  onSave?: (content: string, html: string) => void;
}

type ExplainabilityMode = 'summary' | 'inspect' | 'forensic';

type AIHintSeverity = 'info' | 'provisional' | 'risk';

interface AIHint {
  id: string;
  severity: AIHintSeverity;
  title: string;
  detail: string;
  traceTarget?: TraceTarget;
  insertText?: string;
}

function hintBadge(severity: AIHintSeverity) {
  if (severity === 'risk') {
    return <Badge className="text-[10px] h-5 bg-red-50 text-red-700 border border-red-200 hover:bg-red-50">Legal risk</Badge>;
  }
  if (severity === 'provisional') {
    return <Badge className="text-[10px] h-5 bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-50">Provisional</Badge>;
  }
  return <Badge className="text-[10px] h-5 bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-100">Info</Badge>;
}

function WhyIconButton({
  visible,
  onClick,
  tooltip,
}: {
  visible: boolean;
  onClick?: () => void;
  tooltip: string;
}) {
  return (
    <button
      type="button"
      className={`h-7 w-7 rounded-md flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors ${
        visible ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
      }`}
      aria-label="Open trace"
      title={tooltip}
      onClick={onClick}
    >
      <HelpCircle className="w-4 h-4" />
    </button>
  );
}

export function DocumentEditor({ 
  initialContent = '', 
  placeholder = 'Start drafting your planning document...',
  stageId = 'baseline',
  explainabilityMode = 'summary',
  templateToInsert,
  onOpenTrace,
  onOpenCoDrafter,
  onRequestPatchBundle,
  onSave 
}: DocumentEditorProps) {
  const dispatch = useAppDispatch();
  const { document } = useAppState();
  
  const [commentDraft, setCommentDraft] = useState('');
  const [activeCommentRange, setActiveCommentRange] = useState<{ from: number; to: number } | null>(null);

  // Droppable area for evidence
  const { isOver, setNodeRef } = useDroppable({
    id: 'document-editor',
    data: { type: 'document', stageId }
  });

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Placeholder.configure({
        placeholder,
      }),
      Highlight.configure({
        multicolor: true,
      }),
    ],
    content: document.html || initialContent,
    onUpdate: ({ editor }) => {
      // Auto-save draft
      dispatch({
        type: 'UPDATE_DOCUMENT',
        payload: { html: editor.getHTML(), text: editor.getText() }
      });
    },
    editorProps: {
      attributes: {
        class: 'prose prose-slate max-w-none focus:outline-none min-h-[400px] p-6',
      },
    },
  });

  useEffect(() => {
    if (!editor) return;
    const html = editor.getHTML();
    const text = editor.getText();

    if (!document.html && html) {
      dispatch({
        type: 'UPDATE_DOCUMENT',
        payload: { html, text },
      });
    }
  }, [editor, dispatch, document.html]);

  useEffect(() => {
    if (!editor) return;
    if (!document.html) return;

    const current = editor.getHTML();
    if (current === document.html) return;
    editor.commands.setContent(document.html, false);
  }, [editor, document.html]);

  // Handle template insertion
  useEffect(() => {
    if (templateToInsert && editor) {
      editor.chain().focus().insertContent(templateToInsert.content).run();
      toast.success('Template inserted');
    }
  }, [templateToInsert, editor]);

  const aiHints = useMemo<AIHint[]>(() => {
    const text = document.text || '';
    const citationCount = document.citations?.length ?? 0;
    const hints: AIHint[] = [];

    const hasNumbers = /\d/.test(text);
    if (hasNumbers && citationCount === 0) {
      hints.push({
        id: 'hint-cite-figures',
        severity: 'provisional',
        title: 'Cite key figures',
        detail: 'Numeric claims detected but there are no citations yet.',
        traceTarget: { kind: 'evidence', id: 'ev-affordability', label: 'Affordability evidence (demo)' },
      });
    }

    const mentionsTransport = /\b(A14|transport|rail|connectivity|cycling|bus)\b/i.test(text);
    const hasTransportLimitation = /\b(DfT|connectivity tool|capacity constraints|congestion)\b/i.test(text);
    if (stageId === 'baseline' && mentionsTransport && !hasTransportLimitation) {
      hints.push({
        id: 'hint-limitations',
        severity: 'provisional',
        title: 'Add transport limitations note',
        detail: 'Transport baseline should surface tool limitations and assumptions (capacity, congestion, future growth).',
        insertText:
          '\n\nLimitations: DfT connectivity outputs do not model capacity constraints or future growth scenarios; treat results as indicative only.\n',
        traceTarget: { kind: 'evidence', id: 'ev-transport-dft', label: 'DfT connectivity evidence (demo)' },
      });
    }

    if (stageId === 'casework' && /\bAPPROVE\b/i.test(text) && !/\bcondition/i.test(text)) {
      hints.push({
        id: 'hint-conditions',
        severity: 'info',
        title: 'Draft conditions list',
        detail: 'Recommendation is present; conditions section may need drafting.',
        insertText:
          '\n\nConditions (draft):\n- Secure covered cycle storage (2 spaces)\n- Removal of permitted development rights\n- Retention of front elevation details\n',
        traceTarget: { kind: 'run', label: 'Current run', note: 'Officer conditions checklist is logged as a reasoning artefact (demo).' },
      });
    }

    return hints.slice(0, 3);
  }, [document.text, document.citations, stageId]);

  const proposePatch = useCallback(
    (hint?: AIHint) => {
      if (onRequestPatchBundle) {
        onRequestPatchBundle();
        return;
      }

      onOpenCoDrafter?.();
      toast.info(hint ? `Open Co‑Drafter to resolve: ${hint.title}` : 'Open Co‑Drafter to request a patch bundle');
    },
    [onOpenCoDrafter, onRequestPatchBundle],
  );

  const addCitation = useCallback(() => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to);
    
    dispatch({ 
      type: 'ADD_CITATION', 
      payload: { 
        range: { from, to }, 
        text: selectedText,
        evidenceId: 'pending' // Will be linked when evidence is dropped
      } 
    });
    
    editor.chain().focus().toggleHighlight({ color: '#fef3c7' }).run();
    toast.success('Citation mark added - drop evidence to link');
  }, [editor, dispatch]);

  const addComment = useCallback(() => {
    if (!editor || !commentDraft.trim()) return;
    const { from, to } = editor.state.selection;
    
    dispatch({
      type: 'ADD_COMMENT',
      payload: {
        range: { from, to },
        text: commentDraft,
        author: 'Current User',
      }
    });
    
    editor.chain().focus().toggleHighlight({ color: '#dbeafe' }).run();
    setCommentDraft('');
    setActiveCommentRange(null);
    toast.success('Comment added');
  }, [editor, commentDraft, dispatch]);

  const handleSave = useCallback(() => {
    if (!editor) return;
    const text = editor.getText();
    const html = editor.getHTML();
    onSave?.(text, html);
    toast.success('Document saved');
  }, [editor, onSave]);

  if (!editor) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div 
      ref={setNodeRef}
      className={`h-full flex flex-col bg-white rounded-lg border transition-colors ${
        isOver ? 'border-blue-400 ring-2 ring-blue-100' : 'border-neutral-200'
      }`}
    >
      {/* Toolbar */}
      <div className="border-b border-neutral-200 p-2 flex items-center gap-1 flex-wrap">
        {/* Text Formatting */}
        <div className="flex items-center gap-1 pr-2 border-r border-neutral-200">
          <button
            onClick={() => editor.chain().focus().toggleBold().run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('bold') ? 'bg-slate-100' : ''}`}
            title="Bold"
          >
            <Bold className="w-4 h-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleItalic().run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('italic') ? 'bg-slate-100' : ''}`}
            title="Italic"
          >
            <Italic className="w-4 h-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('heading', { level: 1 }) ? 'bg-slate-100' : ''}`}
            title="Heading 1"
          >
            <Heading1 className="w-4 h-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('heading', { level: 2 }) ? 'bg-slate-100' : ''}`}
            title="Heading 2"
          >
            <Heading2 className="w-4 h-4" />
          </button>
        </div>

        {/* Lists */}
        <div className="flex items-center gap-1 px-2 border-r border-neutral-200">
          <button
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('bulletList') ? 'bg-slate-100' : ''}`}
            title="Bullet List"
          >
            <List className="w-4 h-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('orderedList') ? 'bg-slate-100' : ''}`}
            title="Numbered List"
          >
            <ListOrdered className="w-4 h-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            className={`p-2 rounded hover:bg-slate-100 ${editor.isActive('blockquote') ? 'bg-slate-100' : ''}`}
            title="Quote"
          >
            <Quote className="w-4 h-4" />
          </button>
        </div>

        {/* Planning Tools */}
        <div className="flex items-center gap-1 px-2 border-r border-neutral-200">
          <button
            onClick={addCitation}
            className="p-2 rounded hover:bg-amber-50 text-amber-700"
            title="Add Citation Mark"
          >
            <Bookmark className="w-4 h-4" />
          </button>
          <button
            onClick={() => setActiveCommentRange(editor.state.selection)}
            className="p-2 rounded hover:bg-blue-50 text-blue-700"
            title="Add Comment"
          >
            <MessageSquare className="w-4 h-4" />
          </button>
        </div>

        {/* AI Tools */}
        <div className="flex items-center gap-1 px-2 border-r border-neutral-200">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenCoDrafter?.()}
            disabled={!onOpenCoDrafter}
            className="gap-2 text-violet-700 hover:bg-violet-50 disabled:opacity-40"
          >
            <Sparkles className="w-4 h-4" />
            Co‑Drafter
          </Button>
        </div>

        {/* Undo/Redo */}
        <div className="flex items-center gap-1 px-2 border-r border-neutral-200">
          <button
            onClick={() => editor.chain().focus().undo().run()}
            disabled={!editor.can().undo()}
            className="p-2 rounded hover:bg-slate-100 disabled:opacity-30"
            title="Undo"
          >
            <Undo className="w-4 h-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().redo().run()}
            disabled={!editor.can().redo()}
            className="p-2 rounded hover:bg-slate-100 disabled:opacity-30"
            title="Redo"
          >
            <Redo className="w-4 h-4" />
          </button>
        </div>

        {/* Save */}
        <div className="ml-auto">
          <Button variant="default" size="sm" onClick={handleSave} className="gap-2">
            <FileText className="w-4 h-4" />
            Save Draft
          </Button>
        </div>
      </div>

      {/* Inline AI hints/warnings (compact, officer-facing) */}
      {aiHints.length > 0 && (
        <div className="border-b border-neutral-200 bg-slate-50/50 px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <AlertCircle className="w-4 h-4 text-amber-600" />
              <span className="text-xs font-semibold text-slate-700 truncate">AI review</span>
              <Badge variant="outline" className="text-[10px] bg-white">{aiHints.length} hint{aiHints.length === 1 ? '' : 's'}</Badge>
            </div>
            <span className="text-[11px] text-slate-500">{stageId}</span>
          </div>
          <div className="mt-2 space-y-1">
            {aiHints.map((hint) => (
              <div key={hint.id} className="group flex items-start gap-2 rounded-lg bg-white border border-neutral-200 px-2.5 py-2">
                <div className="flex-shrink-0">{hintBadge(hint.severity)}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-slate-800">{hint.title}</div>
                  {explainabilityMode !== 'summary' ? (
                    <div className="text-[11px] text-slate-600 mt-0.5">{hint.detail}</div>
                  ) : null}
                </div>
                {hint.insertText || hint.traceTarget ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => proposePatch(hint)}
                  >
                    Propose patch
                  </Button>
                ) : null}
                <WhyIconButton
                  visible={explainabilityMode !== 'summary'}
                  tooltip={explainabilityMode === 'forensic' ? 'Open trace' : 'Why? (open trace)'}
                  onClick={() => onOpenTrace?.(hint.traceTarget)}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Comment Input */}
      {activeCommentRange && (
        <div className="border-b border-neutral-200 bg-blue-50/50 p-3">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-4 h-4 text-blue-600" />
            <span className="text-sm font-medium text-blue-800">Add Comment</span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={commentDraft}
              onChange={(e) => setCommentDraft(e.target.value)}
              placeholder="Type your comment..."
              className="flex-1 px-3 py-2 text-sm border border-blue-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
              onKeyDown={(e) => e.key === 'Enter' && addComment()}
            />
            <Button variant="default" size="sm" onClick={addComment}>
              Add
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setActiveCommentRange(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Editor Content */}
      <div className="flex-1 overflow-y-auto">
        <EditorContent editor={editor} />
      </div>

      {/* Drop Zone Indicator */}
      {isOver && (
        <div className="absolute inset-0 bg-blue-50/80 backdrop-blur-sm flex items-center justify-center pointer-events-none rounded-lg">
          <div className="text-center">
            <Bookmark className="w-12 h-12 text-blue-500 mx-auto mb-2" />
            <p className="text-lg font-medium text-blue-700">Drop evidence to cite</p>
            <p className="text-sm text-blue-600">It will be linked at the cursor position</p>
          </div>
        </div>
      )}

      {/* Status Bar */}
      <div className="border-t border-neutral-200 px-4 py-2 flex items-center justify-between text-xs text-slate-500">
        <div className="flex items-center gap-4">
          <span>{editor.storage.characterCount?.characters?.() ?? editor.getText().length} characters</span>
          <span>{document.citations?.length ?? 0} citations</span>
          <span>{document.comments?.length ?? 0} comments</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-emerald-700">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            Ready
          </span>
        </div>
      </div>
    </div>
  );
}
