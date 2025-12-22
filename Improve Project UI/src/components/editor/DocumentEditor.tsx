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

import { useCallback, useState, useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Highlight from '@tiptap/extension-highlight';
import { 
  Bold, Italic, List, ListOrdered, Quote, Heading1, Heading2, 
  MessageSquare, Bookmark, Sparkles, Undo, Redo, FileText, 
  Type, Link, Code, CheckCircle2, AlertCircle, ChevronDown, Loader2
} from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { useDroppable } from '@dnd-kit/core';
import { useAppState, useAppDispatch } from '../../lib/appState';
import { simulateDraft, getStageSuggestions } from '../../lib/aiSimulation';
import { toast } from 'sonner';

interface DocumentEditorProps {
  initialContent?: string;
  placeholder?: string;
  stageId?: string;
  onSave?: (content: string, html: string) => void;
}

interface AISuggestion {
  id: string;
  text: string;
  type: 'inline' | 'block' | 'rewrite';
  accepted: boolean;
}

export function DocumentEditor({ 
  initialContent = '', 
  placeholder = 'Start drafting your planning document...',
  stageId = 'baseline',
  onSave 
}: DocumentEditorProps) {
  const dispatch = useAppDispatch();
  const { document, aiState, currentStageId } = useAppState();
  
  const [showAISuggestions, setShowAISuggestions] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamedText, setStreamedText] = useState('');
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
    content: initialContent || document.content,
    onUpdate: ({ editor }) => {
      // Auto-save draft
      dispatch({
        type: 'UPDATE_DOCUMENT',
        payload: { content: editor.getText() }
      });
    },
    editorProps: {
      attributes: {
        class: 'prose prose-slate max-w-none focus:outline-none min-h-[400px] p-6',
      },
    },
  });

  // Load AI suggestions for current stage
  useEffect(() => {
    const suggestions = getStageSuggestions(stageId);
    setAiSuggestions(suggestions.map((s, i) => ({
      id: `suggestion-${i}`,
      text: s.text,
      type: s.type as 'inline' | 'block' | 'rewrite',
      accepted: false,
    })));
  }, [stageId]);

  const handleAIDraft = useCallback(async () => {
    setIsGenerating(true);
    setStreamedText('');
    dispatch({ type: 'START_AI_GENERATION', payload: { task: 'draft' } });

    await simulateDraft(
      stageId,
      (chunk) => {
        setStreamedText(prev => prev + chunk);
        dispatch({ type: 'UPDATE_AI_STREAM', payload: { text: chunk } });
      },
      () => {
        setIsGenerating(false);
        dispatch({ type: 'COMPLETE_AI_GENERATION' });
        toast.success('Draft generated successfully');
      }
    );
  }, [stageId, dispatch]);

  const insertAISuggestion = useCallback((suggestion: AISuggestion) => {
    if (!editor) return;
    
    if (suggestion.type === 'block') {
      editor.chain().focus().insertContent(`\n\n${suggestion.text}\n\n`).run();
    } else {
      editor.chain().focus().insertContent(suggestion.text).run();
    }
    
    setAiSuggestions(prev => 
      prev.map(s => s.id === suggestion.id ? { ...s, accepted: true } : s)
    );
    toast.success('Suggestion inserted');
  }, [editor]);

  const insertStreamedDraft = useCallback(() => {
    if (!editor || !streamedText) return;
    editor.chain().focus().insertContent(streamedText).run();
    setStreamedText('');
    toast.success('Draft inserted into document');
  }, [editor, streamedText]);

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
            onClick={handleAIDraft}
            disabled={isGenerating}
            className="gap-2 text-violet-700 hover:bg-violet-50"
          >
            {isGenerating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {isGenerating ? 'Generating...' : 'AI Draft'}
          </Button>
          <button
            onClick={() => setShowAISuggestions(!showAISuggestions)}
            className={`p-2 rounded flex items-center gap-1 text-sm ${
              showAISuggestions ? 'bg-violet-100 text-violet-700' : 'hover:bg-slate-100'
            }`}
            title="Toggle AI Suggestions"
          >
            <Type className="w-4 h-4" />
            <ChevronDown className={`w-3 h-3 transition-transform ${showAISuggestions ? 'rotate-180' : ''}`} />
          </button>
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

      {/* AI Suggestions Panel */}
      {showAISuggestions && aiSuggestions.length > 0 && (
        <div className="border-b border-neutral-200 bg-violet-50/50 p-3">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-4 h-4 text-violet-600" />
            <span className="text-sm font-medium text-violet-800">AI Suggestions for {stageId}</span>
          </div>
          <div className="space-y-2">
            {aiSuggestions.filter(s => !s.accepted).map((suggestion) => (
              <div 
                key={suggestion.id}
                className="bg-white rounded-lg p-3 border border-violet-200 flex items-start gap-3"
              >
                <div className="flex-1">
                  <Badge variant="outline" className="text-[10px] mb-1">
                    {suggestion.type}
                  </Badge>
                  <p className="text-sm text-slate-700 line-clamp-2">{suggestion.text}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => insertAISuggestion(suggestion)}
                  className="flex-shrink-0"
                >
                  Insert
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Streaming Draft Preview */}
      {streamedText && (
        <div className="border-b border-neutral-200 bg-green-50/50 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-600" />
              <span className="text-sm font-medium text-green-800">Generated Draft</span>
            </div>
            <Button variant="default" size="sm" onClick={insertStreamedDraft}>
              Insert into Document
            </Button>
          </div>
          <div className="bg-white rounded-lg p-3 border border-green-200 max-h-40 overflow-y-auto">
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{streamedText}</p>
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
          {aiState.isGenerating ? (
            <span className="flex items-center gap-1 text-violet-600">
              <Loader2 className="w-3 h-3 animate-spin" />
              AI generating...
            </span>
          ) : (
            <span className="text-green-600 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              Ready
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
