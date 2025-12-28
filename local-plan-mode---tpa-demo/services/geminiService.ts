import { GoogleGenAI, Type } from "@google/genai";
import { Scenario, Site, TraceResponse, LocationContext } from "../types";
import { MOCK_SCENARIOS, MOCK_SITES } from "../constants";

// Initialize Gemini Client
// The API key is guaranteed to be available in process.env.API_KEY in this environment
const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

const modelId = "gemini-3-flash-preview";

// Helper to clean AI text response which might have escaped newlines incorrectly for JSON
const cleanText = (text: string): string => {
  if (!text) return "";
  // Replace literal \\n with \n to fix markdown rendering issues
  return text.replace(/\\n/g, '\n');
};

const cleanSite = (site: Site): Site => ({
  ...site,
  summary: cleanText(site.summary)
});

const cleanScenario = (scenario: Scenario): Scenario => ({
  ...scenario,
  narrative: cleanText(scenario.narrative)
});

// Helper to recalculate metrics to ensure consistency between sites and scenario definitions
const recalculateMetrics = (scenarios: Scenario[], sites: Site[]): Scenario[] => {
  return scenarios.map(scenario => {
    const includedSites = sites.filter(s => scenario.includedSiteIds.includes(s.id));
    return {
      ...scenario,
      metrics: {
        totalSites: includedSites.length,
        totalCapacity: includedSites.reduce((sum, site) => sum + site.capacity, 0)
      }
    };
  });
};

export const generatePlanningData = async (location: LocationContext): Promise<{ sites: Site[], scenarios: Scenario[] }> => {
  const prompt = `
  SYSTEM: You are an expert urban planner and spatial data analyst.
  
  TASK: Generate a realistic dataset for a Local Plan in **${location.displayName}**.
  
  1. Create 6-8 distinct development sites relevant to the context of ${location.name}. 
     - Use realistic street names or area names found in ${location.name} (e.g. if London, use "High Street", "Station Rd"; if US, use "Main St", "Downtown").
     - Vary the categories (e.g., "Brownfield", "Town Centre", "Industrial Intensification", "Greenfield").
     - Vary constraints (Flood zones, Heritage, Transport safeguarding).
     - Assign realistic capacities (50 - 3000 homes).
     - Give them coordinates x (0-100) and y (0-100) spread out spatially.
  
  2. Create 3 distinct spatial strategy scenarios for this location.
     - Example: "Maximum Growth", "Conservation First", "Transit-Oriented".
     - Assign a subset of the generated site IDs to each scenario.
     - Write a professional narrative for the scenario, specifically referencing ${location.name}.
  
  OUTPUT: Return JSON ONLY matching the schema.
  `;

  try {
    const response = await ai.models.generateContent({
      model: modelId,
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            sites: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  id: { type: Type.STRING },
                  name: { type: Type.STRING },
                  category: { type: Type.STRING },
                  capacity: { type: Type.NUMBER },
                  constraintsCount: { type: Type.NUMBER },
                  accessibilityScore: { type: Type.NUMBER },
                  sustainabilityScore: { type: Type.NUMBER },
                  deliverability: { type: Type.STRING, enum: ["High", "Medium", "Low"] },
                  suitability: { type: Type.STRING, enum: ["High", "Medium", "Low"] },
                  availability: { type: Type.STRING, enum: ["High", "Medium", "Low"] },
                  achievability: { type: Type.STRING, enum: ["High", "Medium", "Low"] },
                  summary: { type: Type.STRING },
                  constraintsList: { type: Type.ARRAY, items: { type: Type.STRING } },
                  coordinates: {
                    type: Type.OBJECT,
                    properties: {
                      x: { type: Type.NUMBER },
                      y: { type: Type.NUMBER }
                    }
                  }
                },
                required: ["id", "name", "capacity", "coordinates", "constraintsList"]
              }
            },
            scenarios: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  id: { type: Type.STRING },
                  label: { type: Type.STRING },
                  description: { type: Type.STRING },
                  narrative: { type: Type.STRING },
                  includedSiteIds: { type: Type.ARRAY, items: { type: Type.STRING } }
                },
                required: ["id", "label", "includedSiteIds"]
              }
            }
          }
        }
      }
    });

    if (response.text) {
      const data = JSON.parse(response.text) as { sites: Site[], scenarios: Scenario[] };
      
      const sites = data.sites.map(cleanSite);
      const scenarios = data.scenarios.map(cleanScenario);
      
      const refinedScenarios = recalculateMetrics(scenarios, sites);
      return { sites, scenarios: refinedScenarios };
    }
    throw new Error("No data returned");

  } catch (error) {
    console.warn("Failed to generate dynamic data, falling back to mocks:", error);
    return { sites: MOCK_SITES, scenarios: MOCK_SCENARIOS };
  }
};

export const generateConstraintAnalysis = async (site: Site, constraint: string): Promise<string> => {
  const prompt = `
  SYSTEM: You are a senior planning officer analyzing specific site constraints.
  
  CONTEXT:
  Site: ${site.name} (${site.category})
  Constraint: "${constraint}"
  
  TASK:
  Provide a concise (2-3 sentences) planning analysis of this specific constraint.
  1. What is the specific implication/risk for this site?
  2. What is the standard mitigation strategy?
  
  TONE: Professional, technical, concise. 
  Do not use markdown. Just plain text.
  `;

  try {
    const response = await ai.models.generateContent({
      model: modelId,
      contents: prompt,
    });
    return cleanText(response.text || "Analysis unavailable.");
  } catch (error) {
    console.error("Analysis Error:", error);
    return "Unable to generate analysis at this time.";
  }
};

export const generateInspectorTrace = async (scenario: Scenario, site: Site): Promise<TraceResponse> => {
  const prompt = `
  SYSTEM: You are an AI planning inspector providing detailed reasoning with evidence for a Local Plan.
  
  USER CONTEXT:
  Scenario: ${scenario.label} - ${scenario.description}
  Site: ${site.name} (${site.category}). Capacity: ${site.capacity}.
  Known Factors:
  - Constraints: ${site.constraintsList.join(", ")}
  - Scores (0-10): Accessibility ${site.accessibilityScore}, Sustainability ${site.sustainabilityScore}.
  - Status: Suitability ${site.suitability}, Availability ${site.availability}, Achievability ${site.achievability}.
  
  INSTRUCTION:
  Explain why this site is selected in this scenario and its planning implications. 
  Cover suitability, accessibility, sustainability, and deliverability. 
  Cite relevant policies (use placeholders like [^1] NPPF para 118 if real context isn't available) or data as evidence.
  
  TASK:
  1. Draft a thorough reasoning in markdown format (list or paragraphs) covering all the above aspects.
  2. Use a formal, evidence-based tone (like an inspector's report).
  3. Return JSON ONLY with shape { "traceMarkdown": string } containing the reasoning.
  `;

  try {
    const response = await ai.models.generateContent({
      model: modelId,
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            traceMarkdown: {
              type: Type.STRING,
              description: "The formatted markdown text of the inspector's reasoning."
            }
          },
          required: ["traceMarkdown"]
        }
      }
    });

    if (response.text) {
      const jsonResponse = JSON.parse(response.text) as TraceResponse;
      return { traceMarkdown: cleanText(jsonResponse.traceMarkdown) };
    } else {
      throw new Error("Empty response from AI");
    }
  } catch (error) {
    console.error("Gemini API Error:", error);
    return {
      traceMarkdown: `**Error generating trace.**\n\nUnable to contact the Inspector AI. Please check your API key configuration.\n\n*Technical Details:* ${error instanceof Error ? error.message : "Unknown error"}`
    };
  }
};