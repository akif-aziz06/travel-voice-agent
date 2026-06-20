"use client";

import type {
  BudgetCardData,
  DestinationCardData,
  HotelsCardData,
  ToolCard,
  VisaCardData,
  WeatherCardData,
} from "../lib/toolCards";

const usd = (n?: number | null) =>
  typeof n === "number" ? `$${n.toLocaleString()}` : "—";

const stars = (n?: number | null) =>
  typeof n === "number" && n > 0 ? "★".repeat(Math.round(n)) : null;

function CardShell({
  accent,
  icon,
  title,
  subtitle,
  children,
}: {
  accent: string;
  icon: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/70 shadow-lg backdrop-blur">
      <div className={`flex items-center gap-3 px-4 py-3 ${accent}`}>
        <span className="text-2xl" aria-hidden>
          {icon}
        </span>
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          {subtitle && <p className="text-xs text-white/70">{subtitle}</p>}
        </div>
      </div>
      <div className="px-4 py-3 text-sm text-zinc-200">{children}</div>
    </div>
  );
}

function DestinationCard({ data }: { data: DestinationCardData }) {
  return (
    <CardShell
      accent="bg-gradient-to-r from-emerald-600 to-teal-600"
      icon="🧭"
      title={data.destination}
      subtitle={[data.budget, data.vibe].filter(Boolean).join(" · ")}
    >
      <div className="space-y-2">
        {data.flight && (
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">✈️ {data.flight.route}</span>
            <span className="font-medium">{usd(data.flight.price_usd)} RT</span>
          </div>
        )}
        {data.hotel && (
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">🏨 {data.hotel.name}</span>
            <span className="font-medium">
              {usd(data.hotel.price_per_night_usd)}/night
            </span>
          </div>
        )}
        {data.hotel?.highlights && (
          <p className="text-xs text-zinc-400">{data.hotel.highlights}</p>
        )}
      </div>
    </CardShell>
  );
}

function BudgetCard({ data }: { data: BudgetCardData }) {
  const rows: [string, number][] = [
    ["Flights", data.breakdown.flights],
    ["Hotels", data.breakdown.hotels],
    ["Food", data.breakdown.food],
    ["Activities", data.breakdown.activities],
  ];
  return (
    <CardShell
      accent="bg-gradient-to-r from-amber-600 to-orange-600"
      icon="🧮"
      title={`${data.destination} — total ${usd(data.total_estimate_usd)}`}
      subtitle={`${data.days} days · ${data.travelers} traveler${
        data.travelers === 1 ? "" : "s"
      }`}
    >
      <div className="space-y-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-zinc-400">{label}</span>
            <span className="font-medium">{usd(value)}</span>
          </div>
        ))}
        {typeof data.per_traveler_usd === "number" && (
          <div className="mt-1 flex items-center justify-between border-t border-white/10 pt-1.5">
            <span className="text-zinc-400">Per traveler</span>
            <span className="font-semibold text-amber-300">
              {usd(data.per_traveler_usd)}
            </span>
          </div>
        )}
      </div>
    </CardShell>
  );
}

function WeatherCard({ data }: { data: WeatherCardData }) {
  return (
    <CardShell
      accent="bg-gradient-to-r from-sky-600 to-cyan-600"
      icon={data.emoji ?? "🌡️"}
      title={
        data.available && typeof data.temperature === "number"
          ? `${Math.round(data.temperature)}${data.temperature_unit ?? "°C"}`
          : "Weather"
      }
      subtitle={data.description}
    >
      {data.available ? (
        <p className="text-zinc-300 capitalize">
          Currently {data.description} at the destination.
        </p>
      ) : (
        <p className="text-zinc-400">Live weather is temporarily unavailable.</p>
      )}
    </CardShell>
  );
}

function VisaCard({ data }: { data: VisaCardData }) {
  const tone = /free|on arrival/i.test(data.requirement)
    ? "text-emerald-300"
    : /required/i.test(data.requirement)
      ? "text-rose-300"
      : "text-amber-300";
  return (
    <CardShell
      accent="bg-gradient-to-r from-violet-600 to-fuchsia-600"
      icon="🛂"
      title={`${data.origin} → ${data.destination}`}
      subtitle="Tourist visa"
    >
      <p className={`text-base font-semibold ${tone}`}>{data.requirement}</p>
      {data.max_stay && (
        <p className="mt-0.5 text-xs text-zinc-400">Max stay: {data.max_stay}</p>
      )}
      {data.details && (
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">
          {data.details}
        </p>
      )}
    </CardShell>
  );
}

function HotelsCard({ data }: { data: HotelsCardData }) {
  return (
    <CardShell
      accent="bg-gradient-to-r from-rose-600 to-pink-600"
      icon="🏨"
      title={`Stays in ${data.city}`}
      subtitle={data.source === "booking" ? "Live · Booking.com" : "Curated picks"}
    >
      <div className="space-y-3">
        {data.hotels.map((h, i) => (
          <div key={h.hotel_id ?? `${h.name}-${i}`} className="flex items-center gap-3">
            {h.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={h.photo_url}
                alt={h.name}
                loading="lazy"
                className="h-14 w-14 shrink-0 rounded-lg object-cover"
              />
            ) : (
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-rose-500/30 to-pink-500/30 text-lg">
                🛏️
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-zinc-100">{h.name}</p>
              <p className="text-xs text-zinc-400">
                {stars(h.rating) ?? "Boutique"}
                {typeof h.price_per_night_usd === "number"
                  ? ` · ${usd(h.price_per_night_usd)}/night`
                  : ""}
              </p>
            </div>
            {typeof h.review_score === "number" && (
              <div className="flex shrink-0 flex-col items-center rounded-lg bg-emerald-500/15 px-2 py-1">
                <span className="text-sm font-bold text-emerald-300">
                  {h.review_score.toFixed(1)}
                </span>
                {h.review_word && (
                  <span className="text-[9px] uppercase tracking-wide text-emerald-400/80">
                    {h.review_word}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
        {data.hotels.length === 0 && (
          <p className="text-zinc-400">No stays found for {data.city}.</p>
        )}
      </div>
    </CardShell>
  );
}

function renderCard(card: ToolCard) {
  switch (card.tool) {
    case "destination":
      return <DestinationCard data={card.data} />;
    case "budget":
      return <BudgetCard data={card.data} />;
    case "weather":
      return <WeatherCard data={card.data} />;
    case "visa":
      return <VisaCard data={card.data} />;
    case "hotels":
      return <HotelsCard data={card.data} />;
    default:
      return null;
  }
}

/**
 * Renders the stack of tool-result cards (newest first).
 */
export default function ToolCards({ cards }: { cards: ToolCard[] }) {
  if (cards.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-zinc-500">
        <span className="text-3xl" aria-hidden>
          🗂️
        </span>
        Trip details, weather, visa info, and hotels will pop up here as Atlas
        works.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 overflow-y-auto p-4">
      {cards.map((card) => (
        <div key={card.id}>{renderCard(card)}</div>
      ))}
    </div>
  );
}
