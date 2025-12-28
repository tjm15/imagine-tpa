export type TraceTargetKind =
  | 'run'
  | 'document'
  | 'site'
  | 'consideration'
  | 'evidence'
  | 'policy'
  | 'constraint'
  | 'tension'
  | 'ai_hint';

export interface TraceTarget {
  kind: TraceTargetKind;
  id?: string;
  label?: string;
  note?: string;
}
