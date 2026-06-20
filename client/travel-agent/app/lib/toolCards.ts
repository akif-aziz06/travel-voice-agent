/**
 * Shared types and a decoder for the structured tool-result payloads the Atlas
 * agent streams over the LiveKit data channel (topic "atlas.tool").
 *
 * The backend (server/main.py `_publish_card`) sends:
 *   { "type": "tool_result", "tool": <name>, "data": {...} }
 */

export const TOOL_TOPIC = "atlas.tool";

export interface DestinationCardData {
  destination: string;
  budget?: string;
  vibe?: string;
  flight?: {
    route?: string;
    price_usd?: number;
    airline?: string;
    duration_hours?: number;
  };
  hotel?: {
    name?: string;
    price_per_night_usd?: number;
    stars?: number;
    highlights?: string;
  };
  tags?: string[];
}

export interface BudgetCardData {
  destination: string;
  days: number;
  travelers: number;
  breakdown: {
    flights: number;
    hotels: number;
    food: number;
    activities: number;
  };
  total_estimate_usd: number;
  per_traveler_usd?: number;
}

export interface WeatherCardData {
  available: boolean;
  latitude?: number;
  longitude?: number;
  temperature?: number | null;
  temperature_unit?: string;
  weather_code?: number;
  description?: string;
  emoji?: string;
}

export interface VisaCardData {
  origin: string;
  destination: string;
  requirement: string;
  details?: string;
  max_stay?: string;
  known?: boolean;
}

export interface HotelEntry {
  name: string;
  hotel_id?: string | number;
  rating?: number | null;
  price_per_night_usd?: number | null;
  currency?: string;
  review_score?: number | null;
  review_word?: string | null;
  photo_url?: string | null;
  highlights?: string | null;
}

export interface HotelsCardData {
  city: string;
  source: "booking" | "mock";
  check_in?: string;
  check_out?: string;
  hotels: HotelEntry[];
}

export type ToolCard =
  | { id: string; tool: "destination"; data: DestinationCardData }
  | { id: string; tool: "budget"; data: BudgetCardData }
  | { id: string; tool: "weather"; data: WeatherCardData }
  | { id: string; tool: "visa"; data: VisaCardData }
  | { id: string; tool: "hotels"; data: HotelsCardData };

export type ToolName = ToolCard["tool"];

const KNOWN_TOOLS: ToolName[] = [
  "destination",
  "budget",
  "weather",
  "visa",
  "hotels",
];

let cardCounter = 0;

/**
 * Decode a raw data-channel payload into a ToolCard, or null if it isn't a
 * recognised tool-result message. Defensive against malformed JSON.
 */
export function decodeToolCard(payload: Uint8Array): ToolCard | null {
  try {
    const text = new TextDecoder().decode(payload);
    const parsed = JSON.parse(text) as {
      type?: string;
      tool?: string;
      data?: unknown;
    };
    if (parsed.type !== "tool_result") return null;
    if (!parsed.tool || !KNOWN_TOOLS.includes(parsed.tool as ToolName)) {
      return null;
    }
    cardCounter += 1;
    return {
      id: `${parsed.tool}-${Date.now()}-${cardCounter}`,
      tool: parsed.tool as ToolName,
      data: parsed.data,
    } as ToolCard;
  } catch {
    return null;
  }
}
