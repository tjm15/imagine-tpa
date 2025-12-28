import { LocationContext } from "../types";

export const searchLocation = async (query: string): Promise<LocationContext | null> => {
  if (!query) return null;

  try {
    // Using OpenStreetMap Nominatim API
    // We add countrycodes=gb to restrict to UK/England as requested.
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1&countrycodes=gb`
    );

    if (!response.ok) {
        console.warn(`Geocoding failed with status: ${response.status}`);
        return null;
    }

    const text = await response.text();
    if (!text) return null;

    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      console.warn("Geocoding response was not valid JSON:", text.substring(0, 100));
      return null;
    }

    if (data && Array.isArray(data) && data.length > 0) {
      const result = data[0];
      
      // Nominatim returns boundingbox as [minLat, maxLat, minLon, maxLon] strings
      const bbox = result.boundingbox.map(Number);
      
      return {
        name: result.name || query,
        displayName: result.display_name,
        coordinates: {
          lat: parseFloat(result.lat),
          lng: parseFloat(result.lon)
        },
        bounds: {
          minLat: bbox[0],
          maxLat: bbox[1],
          minLng: bbox[2],
          maxLng: bbox[3]
        }
      };
    }
    return null;
  } catch (error) {
    console.error("Geocoding failed:", error);
    return null;
  }
};