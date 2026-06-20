"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarVisualizer,
  RoomAudioRenderer,
  useDataChannel,
  useLocalParticipant,
  useVoiceAssistant,
} from "@livekit/components-react";
import Transcript from "./Transcript";
import ToolCards from "./ToolCards";
import { decodeToolCard, TOOL_TOPIC, type ToolCard } from "../lib/toolCards";

/** Human-readable copy for each agent state from useVoiceAssistant. */
const STATE_COPY: Record<string, string> = {
  connecting: "Connecting to Atlas…",
  initializing: "Waking Atlas up…",
  listening: "Listening — go ahead",
  thinking: "Atlas is thinking…",
  speaking: "Atlas is speaking",
  disconnected: "Atlas is offline",
};

const MAX_CARDS = 12;

interface AtlasRoomProps {
  /** Called when the user ends the session from inside the room. */
  onLeave: () => void;
}

/**
 * In-room voice experience. Must be rendered inside a <LiveKitRoom>.
 * Lays out the live transcript and tool-result cards, and owns the voice
 * controls (visualizer, mic mute/unmute, leave).
 */
export default function AtlasRoom({ onLeave }: AtlasRoomProps) {
  const { state, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const [cards, setCards] = useState<ToolCard[]>([]);

  // Subscribe to the agent's structured tool-result payloads (newest first).
  const onToolMessage = useCallback((msg: { payload: Uint8Array }) => {
    const card = decodeToolCard(msg.payload);
    if (card) {
      setCards((prev) => [card, ...prev].slice(0, MAX_CARDS));
    }
  }, []);
  useDataChannel(TOOL_TOPIC, onToolMessage);

  // Ensure the microphone is publishing as soon as we join.
  useEffect(() => {
    localParticipant.setMicrophoneEnabled(true).catch(() => {
      /* user can retry via the mic button if permission was denied */
    });
  }, [localParticipant]);

  const toggleMic = () => {
    localParticipant
      .setMicrophoneEnabled(!isMicrophoneEnabled)
      .catch((err: unknown) => console.error("Failed to toggle microphone", err));
  };

  const statusText = STATE_COPY[state] ?? "Ready";

  return (
    <div className="flex w-full max-w-5xl flex-col gap-4">
      {/* Plays the agent's TTS audio track automatically (no manual trigger). */}
      <RoomAudioRenderer />

      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        {/* Left: conversation + voice controls */}
        <section className="flex h-[60vh] min-h-[420px] flex-col rounded-2xl border border-white/10 bg-zinc-900/50">
          <div className="flex-1 overflow-hidden">
            <Transcript />
          </div>

          {/* Voice control bar */}
          <div className="flex items-center gap-3 border-t border-white/10 px-4 py-3">
            <div className="flex h-10 flex-1 items-center">
              <BarVisualizer
                state={state}
                barCount={7}
                trackRef={audioTrack}
                className="h-8 w-full max-w-[160px]"
                options={{ minHeight: 6 }}
              />
            </div>

            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-300">
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  state === "speaking"
                    ? "bg-emerald-400"
                    : state === "listening"
                      ? "bg-sky-400"
                      : "bg-zinc-500"
                }`}
                aria-hidden
              />
              <span className="hidden sm:inline">{statusText}</span>
            </div>

            <button
              type="button"
              onClick={toggleMic}
              aria-pressed={!isMicrophoneEnabled}
              className={`flex h-10 items-center justify-center rounded-full px-4 text-sm font-semibold transition-colors ${
                isMicrophoneEnabled
                  ? "bg-white text-black hover:bg-zinc-200"
                  : "bg-red-500/90 text-white hover:bg-red-500"
              }`}
            >
              {isMicrophoneEnabled ? "Mute" : "Unmute"}
            </button>

            <button
              type="button"
              onClick={onLeave}
              className="flex h-10 items-center justify-center rounded-full border border-white/20 px-4 text-sm font-semibold text-zinc-200 transition-colors hover:bg-white/10"
            >
              End
            </button>
          </div>
        </section>

        {/* Right: tool-result cards */}
        <section className="h-[60vh] min-h-[420px] overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/50">
          <ToolCards cards={cards} />
        </section>
      </div>
    </div>
  );
}
