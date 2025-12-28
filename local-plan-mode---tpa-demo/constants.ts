import { Scenario, Site } from './types';

export const MOCK_SITES: Site[] = [
  {
    id: "regis_road",
    name: "Regis Road",
    category: "Mixed Use Intensification",
    capacity: 1000,
    constraintsCount: 1,
    accessibilityScore: 8.5,
    sustainabilityScore: 7.0,
    deliverability: "High",
    suitability: "High",
    availability: "High",
    achievability: "Medium",
    summary: "Large brownfield site near Kentish Town. Excellent transport connectivity. Key focus on industrial intensification alongside residential.",
    constraintsList: ["Rail Infrastructure", "Industrial Protection"],
    coordinates: { x: 45, y: 30 }
  },
  {
    id: "murphy_yard",
    name: "Murphy's Yard",
    category: "Major Regeneration",
    capacity: 750,
    constraintsCount: 2,
    accessibilityScore: 6.5,
    sustainabilityScore: 7.2,
    deliverability: "Medium",
    suitability: "Medium",
    availability: "High",
    achievability: "Medium",
    summary: "Significant regeneration opportunity. Infrastructure upgrades required to unlock full potential. Connects Gospel Oak to Kentish Town.",
    constraintsList: ["Heath View Cone", "Rail Access"],
    coordinates: { x: 40, y: 25 }
  },
  {
    id: "o2_centre",
    name: "O2 Centre",
    category: "Town Centre",
    capacity: 1800,
    constraintsCount: 0,
    accessibilityScore: 9.5,
    sustainabilityScore: 8.0,
    deliverability: "High",
    suitability: "High",
    availability: "High",
    achievability: "High",
    summary: "Prime town centre location with exceptional transit links. Suitable for high-density mixed-use development.",
    constraintsList: [],
    coordinates: { x: 35, y: 40 }
  },
  {
    id: "euston_station",
    name: "Euston Station Over-Station",
    category: "Strategic Hub",
    capacity: 2200,
    constraintsCount: 3,
    accessibilityScore: 10,
    sustainabilityScore: 9.0,
    deliverability: "Low",
    suitability: "High",
    availability: "Medium",
    achievability: "Low",
    summary: "Nationally significant transport hub. Complex engineering constraints but massive potential for central London housing.",
    constraintsList: ["HS2 Safeguarding", "Heritage Assets", "Strategic View"],
    coordinates: { x: 55, y: 70 }
  },
  {
    id: "camley_street",
    name: "Camley Street",
    category: "Knowledge Quarter Extension",
    capacity: 500,
    constraintsCount: 1,
    accessibilityScore: 8.0,
    sustainabilityScore: 8.5,
    deliverability: "High",
    suitability: "High",
    availability: "High",
    achievability: "High",
    summary: "Extension of the Knowledge Quarter. Focus on lab-enabled space and housing. Canal-side location offers placemaking benefits.",
    constraintsList: ["Canal Conservation"],
    coordinates: { x: 60, y: 65 }
  },
  {
    id: "mount_pleasant",
    name: "Mount Pleasant",
    category: "Infill",
    capacity: 300,
    constraintsCount: 1,
    accessibilityScore: 7.0,
    sustainabilityScore: 6.0,
    deliverability: "Medium",
    suitability: "Medium",
    availability: "Medium",
    achievability: "Medium",
    summary: "Historic sorting office site. constrained by heritage listings but offers central housing capacity.",
    constraintsList: ["Listed Buildings"],
    coordinates: { x: 70, y: 80 }
  }
];

export const MOCK_SCENARIOS: Scenario[] = [
  {
    id: "growth",
    label: "Maximum Growth",
    description: "Maximises housing delivery across all opportunity areas.",
    metrics: { totalSites: 6, totalCapacity: 6550 },
    narrative: "**Maximum Growth Strategy**\n\nThis strategy concentrates development in all major opportunity areas, aiming to deliver the maximum number of homes across the borough. It leverages large brownfield sites such as **Euston Station** and **Regis Road** to meet housing targets, while intensifying mixed-use development in town centres. The trade-off is higher infrastructure demand and potential impacts on conservation areas, mitigated by robust planning obligations.",
    includedSiteIds: ["regis_road", "murphy_yard", "o2_centre", "euston_station", "camley_street", "mount_pleasant"]
  },
  {
    id: "knowledge_quarter",
    label: "Innovation-Led",
    description: "Focuses density around the Knowledge Quarter and Tech hubs.",
    metrics: { totalSites: 3, totalCapacity: 3450 },
    narrative: "**Innovation-Led Strategy**\n\nThis focused approach prioritizes the expansion of the Knowledge Quarter. Allocations are clustered around **Camley Street** and **Euston**, emphasizing employment-led mixed use. While housing delivery is lower than the Growth strategy, it maximizes economic output and reinforces the borough's status as a global science hub.",
    includedSiteIds: ["euston_station", "camley_street", "murphy_yard"]
  },
  {
    id: "town_centre",
    label: "Polycentric",
    description: "Distributes growth to strengthen town centres.",
    metrics: { totalSites: 3, totalCapacity: 3100 },
    narrative: "**Polycentric / Town Centre Strategy**\n\nBy distributing growth to established centres like the **O2 Centre** and **Regis Road**, this strategy aims to revitalize high streets and reduce pressure on central London infrastructure. It supports a '15-minute city' concept, ensuring new homes are close to existing amenities and transport nodes.",
    includedSiteIds: ["o2_centre", "regis_road", "mount_pleasant"]
  }
];