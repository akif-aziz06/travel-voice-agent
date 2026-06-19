"use client";

import { useCallback, useState } from "react";
import { LiveKitRoom } from "@livekit/components-react";
import "@livekit/components-styles";
import AtlasRoom from "./components/AtlasRoom";

const TOKEN_ENDPOINT =
  process.env.NEXT_PUBLIC_LK_TOKEN_ENDPOINT ?? "http://localhost:8000/api/token";

type ConnectionPhase = "idle" | "connecting" | "connected" | "error";

interface SessionCredentials {
  token: string;
  serverUrl: string;
}

/**
 * Atlas voice client. Fetches a short-lived LiveKit token from the FastAPI
 * token service, then hands it to <LiveKitRoom> which manages the WebRTC
 * connection. The Atlas agent worker auto-joins the room and speaks first.
 */
export default function Home() {
  const [phase, setPhase] = useState<ConnectionPhase>("idle");
  const [creds, setCreds] = useState<SessionCredentials | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async () => {
    setPhase("connecting");
    setError(null);
    try {
      const res = await fetch(TOKEN_ENDPOINT, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`Token request failed (${res.status})`);
      }
      const data = (await res.json()) as Partial<SessionCredentials>;
      if (!data.token || !data.serverUrl) {
        throw new Error("Token response missing token or serverUrl");
      }
      setCreds({ token: data.token, serverUrl: data.serverUrl });
      setPhase("connected");
    } catch (err) {
      console.error("Failed to start Atlas session", err);
      setError(err instanceof Error ? err.message : "Unknown error");
      setPhase("error");
    }
  }, []);

  const disconnect = useCallback(() => {
    setCreds(null);
    setPhase("idle");
  }, []);

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-10 bg-zinc-950 px-6 py-16 text-zinc-50">
      <header className="flex flex-col items-center gap-2 text-center">
        <span className="text-4xl" aria-hidden>
          🌍
        </span>
        <h1 className="text-3xl font-semibold tracking-tight">Atlas</h1>
        <p className="max-w-sm text-sm text-zinc-400">
          Your voice-first travel concierge. Tell Atlas your budget and vibe —
          get one perfect trip, no scrolling.
        </p>
      </header>

      {phase === "connected" && creds ? (
        <LiveKitRoom
          token={creds.token}
          serverUrl={creds.serverUrl}
          connect
          audio
          video={false}
          onDisconnected={disconnect}
          className="flex w-full flex-col items-center"
        >
          <AtlasRoom onLeave={disconnect} />
        </LiveKitRoom>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <button
            type="button"
            onClick={connect}
            disabled={phase === "connecting"}
            className="flex h-14 items-center justify-center gap-3 rounded-full bg-white px-8 text-base font-semibold text-black transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {phase === "connecting" ? "Connecting…" : "Start talking to Atlas"}
          </button>
          {phase === "error" && error && (
            <p className="max-w-sm text-center text-sm text-red-400">
              Couldn&apos;t connect: {error}. Make sure the token service is
              running on port 8000.
            </p>
          )}
        </div>
      )}
    </main>
  );
}
