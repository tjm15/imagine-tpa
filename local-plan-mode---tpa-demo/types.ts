export interface ScenarioMetrics {
  totalSites: number;
  totalCapacity: number;
}

export interface Scenario {
  id: string;
  label: string;
  description: string;
  metrics: ScenarioMetrics;
  narrative: string;
  includedSiteIds: string[];
}

export type RAGStatus = 'High' | 'Medium' | 'Low'; // Maps to Green, Amber, Red concept

export interface Site {
  id: string;
  name: string;
  category: string;
  capacity: number;
  constraintsCount: number;
  accessibilityScore: number; // 0-10
  sustainabilityScore: number; // 0-10
  deliverability: RAGStatus;
  suitability: RAGStatus;
  availability: RAGStatus;
  achievability: RAGStatus;
  summary: string;
  constraintsList: string[];
  coordinates: { x: number; y: number }; // For mock map plotting (0-100 scale)
}

export interface TraceResponse {
  traceMarkdown: string;
}

export interface BoundingBox {
  minLat: number;
  maxLat: number;
  minLng: number;
  maxLng: number;
}

export interface LocationContext {
  name: string;
  displayName: string;
  coordinates: { lat: number; lng: number };
  bounds: BoundingBox;
}