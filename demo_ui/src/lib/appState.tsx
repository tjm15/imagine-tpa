/**
 * Global Application State Management
 * 
 * Provides React Context for managing the demo's interactive state including:
 * - Current CULP stage and workspace mode
 * - Document content and editing state
 * - Cited evidence and considerations
 * - Reasoning moves progress
 * - AI generation state
 * - UI interaction state (modals, selections, etc.)
 */

import React, { createContext, useContext, useReducer, useCallback, ReactNode } from 'react';
import { 
  ReasoningMove, 
  Consideration, 
  EvidenceCard, 
  PolicyChip,
  MoveEvent,
  CulpStage,
  mockConsiderations
} from '../fixtures/mockData';

// ============================================================================
// STATE TYPES
// ============================================================================

export interface Citation {
  id: string;
  evidenceId: string;
  position: number; // cursor position in document
  insertedAt: string;
}

export interface Comment {
  id: string;
  text: string;
  author: string;
  position: number;
  resolved: boolean;
  createdAt: string;
  replies: { author: string; text: string; createdAt: string }[];
}

export interface AIGenerationState {
  isGenerating: boolean;
  generationType: 'draft' | 'suggestion' | 'balance' | 'gateway' | 'inspector' | null;
  streamedText: string;
  progress: number; // 0-100
  error: string | null;
}

export interface DocumentState {
  html: string;
  text: string;
  citations: Citation[];
  comments: Comment[];
  isDirty: boolean;
  lastSaved: string | null;
}

export interface NotificationItem {
  id: string;
  type: 'info' | 'warning' | 'error' | 'success' | 'ai';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  actionLabel?: string;
  actionTarget?: string;
}

export interface AppState {
  // Workspace
  currentStageId: string;
  selectedDeliverableId: string | null;
  
  // Document
  document: DocumentState;

  // Map (plan-state overlays)
  highlightedSiteId: string | null;
  adjustedSiteIds: Set<string>;
  
  // Evidence & Policy
  citedEvidence: Set<string>;
  selectedEvidence: string | null;
  selectedPolicy: string | null;
  
  // Considerations
  considerations: Consideration[];
  selectedConsideration: string | null;
  
  // Reasoning
  reasoningMoves: Record<ReasoningMove, 'complete' | 'in-progress' | 'pending'>;
  currentMove: ReasoningMove;
  
  // AI
  aiState: AIGenerationState;
  pendingSuggestions: Array<{
    id: string;
    type: 'content' | 'evidence' | 'warning' | 'question';
    text: string;
    context: string;
    confidence: 'high' | 'medium' | 'low';
  }>;
  
  // UI State
  activeModal: string | null;
  modalData: Record<string, unknown>;
  notifications: NotificationItem[];
  searchQuery: string;
  filterStatus: string | null;
  
  // Undo/Redo
  undoStack: AppState[];
  redoStack: AppState[];
}

// ============================================================================
// ACTIONS
// ============================================================================

type AppAction =
  | { type: 'SET_STAGE'; payload: { stageId: string } }
  | { type: 'SELECT_DELIVERABLE'; payload: { deliverableId: string | null } }
  | { type: 'UPDATE_DOCUMENT'; payload: { html: string; text: string } }
  | { type: 'ADD_CITATION'; payload: { evidenceId: string; position?: number; text?: string; range?: unknown; citation?: unknown } }
  | { type: 'REMOVE_CITATION'; payload: { citationId: string } }
  | { type: 'ADD_COMMENT'; payload: { text: string; position?: number; range?: unknown; author?: string } }
  | { type: 'RESOLVE_COMMENT'; payload: { commentId: string } }
  | { type: 'REPLY_TO_COMMENT'; payload: { commentId: string; text: string } }
  | { type: 'CITE_EVIDENCE'; payload: { evidenceId: string } }
  | { type: 'UNCITE_EVIDENCE'; payload: { evidenceId: string } }
  | { type: 'SELECT_EVIDENCE'; payload: { evidenceId: string | null } }
  | { type: 'SELECT_POLICY'; payload: { policyId: string | null } }
  | { type: 'ADD_CONSIDERATION'; payload: Consideration }
  | { type: 'UPDATE_CONSIDERATION'; payload: { id: string; updates: Partial<Consideration> } }
  | { type: 'REMOVE_CONSIDERATION'; payload: { id: string } }
  | { type: 'REORDER_CONSIDERATIONS'; payload: { considerations: Consideration[] } }
  | { type: 'SELECT_CONSIDERATION'; payload: { id: string | null } }
  | { type: 'ADVANCE_MOVE'; payload: { move: ReasoningMove } }
  | { type: 'SET_MOVE_STATUS'; payload: { move: ReasoningMove; status: 'complete' | 'in-progress' | 'pending' } }
  | { type: 'START_AI_GENERATION'; payload: { task: string } }
  | { type: 'UPDATE_AI_STREAM'; payload: { text: string; progress?: number } }
  | { type: 'COMPLETE_AI_GENERATION' }
  | { type: 'FAIL_AI_GENERATION'; payload: { error: string } }
  | { type: 'ADD_SUGGESTION'; payload: { suggestion: AppState['pendingSuggestions'][0] } }
  | { type: 'DISMISS_SUGGESTION'; payload: { id: string } }
  | { type: 'ACCEPT_SUGGESTION'; payload: { id: string } }
  | { type: 'OPEN_MODAL'; payload: { modalId: string; data?: Record<string, unknown> } }
  | { type: 'CLOSE_MODAL' }
  | { type: 'ADD_NOTIFICATION'; payload: { notification: Omit<NotificationItem, 'id' | 'timestamp' | 'read'> } }
  | { type: 'MARK_NOTIFICATION_READ'; payload: { id: string } }
  | { type: 'CLEAR_NOTIFICATIONS' }
  | { type: 'SET_SEARCH_QUERY'; payload: { query: string } }
  | { type: 'SET_FILTER_STATUS'; payload: { status: string | null } }
  | { type: 'APPLY_PATCH_EFFECTS'; payload: { document?: { html: string; text: string }; adjustedSiteIds?: string[]; highlightedSiteId?: string | null } }
  | { type: 'RESTORE_PATCH_SNAPSHOT'; payload: { snapshot: { documentHtml: string; documentText: string; adjustedSiteIds: string[]; highlightedSiteId: string | null } } }
  | { type: 'UNDO' }
  | { type: 'REDO' }
  | { type: 'RESET_DEMO' };

// ============================================================================
// INITIAL STATE
// ============================================================================

const initialState: AppState = {
  currentStageId: 'baseline',
  selectedDeliverableId: null,
  
  document: {
    html: '',
    text: '',
    citations: [],
    comments: [],
    isDirty: false,
    lastSaved: null,
  },

  highlightedSiteId: null,
  adjustedSiteIds: new Set(),
  
  citedEvidence: new Set(),
  selectedEvidence: null,
  selectedPolicy: null,
  
  considerations: mockConsiderations,
  selectedConsideration: null,
  
  reasoningMoves: {
    framing: 'complete',
    issues: 'complete',
    evidence: 'in-progress',
    interpretation: 'pending',
    considerations: 'pending',
    balance: 'pending',
    negotiation: 'pending',
    positioning: 'pending',
  },
  currentMove: 'evidence',
  
  aiState: {
    isGenerating: false,
    generationType: null,
    streamedText: '',
    progress: 0,
    error: null,
  },
  pendingSuggestions: [],
  
  activeModal: null,
  modalData: {},
  notifications: [],
  searchQuery: '',
  filterStatus: null,
  
  undoStack: [],
  redoStack: [],
};

// ============================================================================
// REDUCER
// ============================================================================

function appReducer(state: AppState, action: AppAction): AppState {
  // Save current state for undo (except for undo/redo actions)
  const saveForUndo = !['UNDO', 'REDO', 'UPDATE_AI_STREAM', 'START_AI_GENERATION'].includes(action.type);
  const newUndoStack = saveForUndo 
    ? [...state.undoStack.slice(-50), { ...state, undoStack: [], redoStack: [] }]
    : state.undoStack;

  switch (action.type) {
    case 'SET_STAGE':
      return { ...state, currentStageId: action.payload.stageId, undoStack: newUndoStack, redoStack: [] };

    case 'SELECT_DELIVERABLE':
      return { ...state, selectedDeliverableId: action.payload.deliverableId };

    case 'UPDATE_DOCUMENT':
      return {
        ...state,
        document: {
          ...state.document,
          html: action.payload.html,
          text: action.payload.text,
          isDirty: true,
        },
        undoStack: newUndoStack,
        redoStack: [],
      };

    case 'ADD_CITATION': {
      const citation: Citation = {
        id: `cit-${Date.now()}`,
        evidenceId: action.payload.evidenceId,
        position: action.payload.position || 0,
        insertedAt: new Date().toISOString(),
      };
      return {
        ...state,
        document: {
          ...state.document,
          citations: [...state.document.citations, citation],
          isDirty: true,
        },
        citedEvidence: new Set([...state.citedEvidence, action.payload.evidenceId]),
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'REMOVE_CITATION': {
      const citations = state.document.citations.filter(c => c.id !== action.payload.citationId);
      const removedCitation = state.document.citations.find(c => c.id === action.payload.citationId);
      const stillCited = citations.some(c => c.evidenceId === removedCitation?.evidenceId);
      const newCitedEvidence = new Set(state.citedEvidence);
      if (!stillCited && removedCitation) {
        newCitedEvidence.delete(removedCitation.evidenceId);
      }
      return {
        ...state,
        document: { ...state.document, citations, isDirty: true },
        citedEvidence: newCitedEvidence,
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'ADD_COMMENT': {
      const comment: Comment = {
        id: `com-${Date.now()}`,
        text: action.payload.text,
        author: action.payload.author || 'Sarah Mitchell',
        position: action.payload.position || 0,
        resolved: false,
        createdAt: new Date().toISOString(),
        replies: [],
      };
      return {
        ...state,
        document: {
          ...state.document,
          comments: [...state.document.comments, comment],
        },
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'RESOLVE_COMMENT':
      return {
        ...state,
        document: {
          ...state.document,
          comments: state.document.comments.map(c =>
            c.id === action.payload.commentId ? { ...c, resolved: true } : c
          ),
        },
      };

    case 'REPLY_TO_COMMENT':
      return {
        ...state,
        document: {
          ...state.document,
          comments: state.document.comments.map(c =>
            c.id === action.payload.commentId
              ? {
                  ...c,
                  replies: [
                    ...c.replies,
                    { author: 'Sarah Mitchell', text: action.payload.text, createdAt: new Date().toISOString() },
                  ],
                }
              : c
          ),
        },
      };

    case 'CITE_EVIDENCE':
      return {
        ...state,
        citedEvidence: new Set([...state.citedEvidence, action.payload.evidenceId]),
      };

    case 'UNCITE_EVIDENCE': {
      const newCited = new Set(state.citedEvidence);
      newCited.delete(action.payload.evidenceId);
      return { ...state, citedEvidence: newCited };
    }

    case 'SELECT_EVIDENCE':
      return { ...state, selectedEvidence: action.payload.evidenceId };

    case 'SELECT_POLICY':
      return { ...state, selectedPolicy: action.payload.policyId };

    case 'ADD_CONSIDERATION': {
      return {
        ...state,
        considerations: [...state.considerations, action.payload],
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'UPDATE_CONSIDERATION':
      return {
        ...state,
        considerations: state.considerations.map(c =>
          c.id === action.payload.id ? { ...c, ...action.payload.updates } : c
        ),
        undoStack: newUndoStack,
        redoStack: [],
      };

    case 'REMOVE_CONSIDERATION':
      return {
        ...state,
        considerations: state.considerations.filter(c => c.id !== action.payload.id),
        undoStack: newUndoStack,
        redoStack: [],
      };

    case 'REORDER_CONSIDERATIONS': {
      return {
        ...state,
        considerations: action.payload.considerations,
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'SELECT_CONSIDERATION':
      return { ...state, selectedConsideration: action.payload.id };

    case 'ADVANCE_MOVE': {
      const moveOrder: ReasoningMove[] = [
        'framing', 'issues', 'evidence', 'interpretation',
        'considerations', 'balance', 'negotiation', 'positioning'
      ];
      const currentIndex = moveOrder.indexOf(action.payload.move);
      const nextMove = moveOrder[currentIndex + 1] || 'positioning';
      
      return {
        ...state,
        reasoningMoves: {
          ...state.reasoningMoves,
          [action.payload.move]: 'complete',
          [nextMove]: currentIndex < moveOrder.length - 1 ? 'in-progress' : 'complete',
        },
        currentMove: nextMove,
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'SET_MOVE_STATUS':
      return {
        ...state,
        reasoningMoves: { ...state.reasoningMoves, [action.payload.move]: action.payload.status },
      };

    case 'START_AI_GENERATION':
      return {
        ...state,
        aiState: {
          isGenerating: true,
          generationType: action.payload.task as AIGenerationState['generationType'],
          streamedText: '',
          progress: 0,
          error: null,
        },
      };

    case 'UPDATE_AI_STREAM':
      const nextProgress = typeof action.payload.progress === 'number'
        ? Math.max(0, Math.min(99, Math.round(action.payload.progress)))
        : Math.min(95, state.aiState.progress + 5);

      return {
        ...state,
        aiState: {
          ...state.aiState,
          streamedText: action.payload.text,
          progress: nextProgress,
        },
      };

    case 'COMPLETE_AI_GENERATION':
      return {
        ...state,
        aiState: {
          ...state.aiState,
          isGenerating: false,
          progress: 100,
        },
      };

    case 'FAIL_AI_GENERATION':
      return {
        ...state,
        aiState: {
          ...state.aiState,
          isGenerating: false,
          error: action.payload.error,
        },
      };

    case 'ADD_SUGGESTION':
      return {
        ...state,
        pendingSuggestions: [...state.pendingSuggestions, action.payload.suggestion],
      };

    case 'DISMISS_SUGGESTION':
      return {
        ...state,
        pendingSuggestions: state.pendingSuggestions.filter(s => s.id !== action.payload.id),
      };

    case 'ACCEPT_SUGGESTION':
      return {
        ...state,
        pendingSuggestions: state.pendingSuggestions.filter(s => s.id !== action.payload.id),
      };

    case 'OPEN_MODAL':
      return {
        ...state,
        activeModal: action.payload.modalId,
        modalData: action.payload.data || {},
      };

    case 'CLOSE_MODAL':
      return {
        ...state,
        activeModal: null,
        modalData: {},
      };

    case 'ADD_NOTIFICATION': {
      const notification: NotificationItem = {
        ...action.payload.notification,
        id: `notif-${Date.now()}`,
        timestamp: new Date().toISOString(),
        read: false,
      };
      return {
        ...state,
        notifications: [notification, ...state.notifications].slice(0, 50),
      };
    }

    case 'MARK_NOTIFICATION_READ':
      return {
        ...state,
        notifications: state.notifications.map(n =>
          n.id === action.payload.id ? { ...n, read: true } : n
        ),
      };

    case 'CLEAR_NOTIFICATIONS':
      return { ...state, notifications: [] };

    case 'SET_SEARCH_QUERY':
      return { ...state, searchQuery: action.payload.query };

    case 'SET_FILTER_STATUS':
      return { ...state, filterStatus: action.payload.status };

    case 'APPLY_PATCH_EFFECTS': {
      const nextDocument = action.payload.document
        ? {
            ...state.document,
            html: action.payload.document.html,
            text: action.payload.document.text,
            isDirty: true,
          }
        : state.document;

      const nextAdjustedSiteIds = Array.isArray(action.payload.adjustedSiteIds)
        ? new Set(action.payload.adjustedSiteIds)
        : state.adjustedSiteIds;

      const nextHighlightedSiteId = action.payload.highlightedSiteId !== undefined
        ? action.payload.highlightedSiteId
        : state.highlightedSiteId;

      return {
        ...state,
        document: nextDocument,
        adjustedSiteIds: nextAdjustedSiteIds,
        highlightedSiteId: nextHighlightedSiteId,
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'RESTORE_PATCH_SNAPSHOT': {
      const { snapshot } = action.payload;
      return {
        ...state,
        document: {
          ...state.document,
          html: snapshot.documentHtml,
          text: snapshot.documentText,
          isDirty: true,
        },
        adjustedSiteIds: new Set(snapshot.adjustedSiteIds),
        highlightedSiteId: snapshot.highlightedSiteId,
        undoStack: newUndoStack,
        redoStack: [],
      };
    }

    case 'UNDO':
      if (state.undoStack.length === 0) return state;
      const previousState = state.undoStack[state.undoStack.length - 1];
      return {
        ...previousState,
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [{ ...state, undoStack: [], redoStack: [] }, ...state.redoStack],
      };

    case 'REDO':
      if (state.redoStack.length === 0) return state;
      const nextState = state.redoStack[0];
      return {
        ...nextState,
        undoStack: [...state.undoStack, { ...state, undoStack: [], redoStack: [] }],
        redoStack: state.redoStack.slice(1),
      };

    case 'RESET_DEMO':
      return { ...initialState };

    default:
      return state;
  }
}

// ============================================================================
// CONTEXT
// ============================================================================

interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
  
  // Convenience actions
  setStage: (stageId: string) => void;
  selectDeliverable: (id: string | null) => void;
  updateDocument: (html: string, text: string) => void;
  addCitation: (evidenceId: string, position: number) => void;
  addComment: (text: string, position: number) => void;
  citeEvidence: (evidenceId: string) => void;
  addConsideration: (consideration: Consideration) => void;
  advanceMove: (move: ReasoningMove) => void;
  openModal: (modal: string, data?: Record<string, unknown>) => void;
  closeModal: () => void;
  notify: (type: NotificationItem['type'], title: string, message: string) => void;
  undo: () => void;
  redo: () => void;
  resetDemo: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  const setStage = useCallback((stageId: string) => {
    dispatch({ type: 'SET_STAGE', payload: { stageId } });
  }, []);

  const selectDeliverable = useCallback((id: string | null) => {
    dispatch({ type: 'SELECT_DELIVERABLE', payload: { deliverableId: id } });
  }, []);

  const updateDocument = useCallback((html: string, text: string) => {
    dispatch({ type: 'UPDATE_DOCUMENT', payload: { html, text } });
  }, []);

  const addCitation = useCallback((evidenceId: string, position: number) => {
    dispatch({ type: 'ADD_CITATION', payload: { evidenceId, position } });
  }, []);

  const addComment = useCallback((text: string, position: number) => {
    dispatch({ type: 'ADD_COMMENT', payload: { text, position } });
  }, []);

  const citeEvidence = useCallback((evidenceId: string) => {
    dispatch({ type: 'CITE_EVIDENCE', payload: { evidenceId } });
  }, []);

  const addConsideration = useCallback((consideration: Consideration) => {
    dispatch({ 
      type: 'ADD_CONSIDERATION', 
      payload: consideration
    });
  }, []);

  const advanceMove = useCallback((move: ReasoningMove) => {
    dispatch({ type: 'ADVANCE_MOVE', payload: { move } });
  }, []);

  const openModal = useCallback((modal: string, data?: Record<string, unknown>) => {
    dispatch({ type: 'OPEN_MODAL', payload: { modalId: modal, data } });
  }, []);

  const closeModal = useCallback(() => {
    dispatch({ type: 'CLOSE_MODAL' });
  }, []);

  const notify = useCallback((type: NotificationItem['type'], title: string, message: string) => {
    dispatch({ type: 'ADD_NOTIFICATION', payload: { notification: { type, title, message } } });
  }, []);

  const undo = useCallback(() => {
    dispatch({ type: 'UNDO' });
  }, []);

  const redo = useCallback(() => {
    dispatch({ type: 'REDO' });
  }, []);

  const resetDemo = useCallback(() => {
    dispatch({ type: 'RESET_DEMO' });
  }, []);

  const value: AppContextValue = {
    state,
    dispatch,
    setStage,
    selectDeliverable,
    updateDocument,
    addCitation,
    addComment,
    citeEvidence,
    addConsideration,
    advanceMove,
    openModal,
    closeModal,
    notify,
    undo,
    redo,
    resetDemo,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppState() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppState must be used within AppStateProvider');
  }
  // Return state properties directly for easier destructuring
  return {
    ...context.state,
    // Also include convenience methods
    openModal: context.openModal,
    closeModal: context.closeModal,
    notify: context.notify,
    undo: context.undo,
    redo: context.redo,
    resetDemo: context.resetDemo,
  };
}

export function useAppDispatch() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppDispatch must be used within AppStateProvider');
  }
  return context.dispatch;
}
