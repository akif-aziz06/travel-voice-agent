"use client";

import { useEffect } from "react";
import {
  BarVisualizer,
  RoomAudioRenderer,
  useLocalParticipant,
  useVoiceAssistant,
} from "@livekit/components-react";

/**
 * Human-readable copy for each Atlas/agent state surfaced by useVoiceAssistant.
 * States: "disconnected" | "connecting" | "initializing"
 *       | "listening" | "thinking" | "speaking".
 */
const STATE_COPY: Record<string, string> = {
  connecting: "Connecting to Atlas…",
  initializing: "Waking Atlas up…",
  listening: "Listening — go ahead",
  thinking: "Atlas is thinking…",
  speaking: "Atlas is speaking",
  disconnected: "Atlas is offline",
};

interface AtlasRoomProps {
  /** Called when the user ends the session from inside the room. */
  onLeave: () => void;
}

/**
 * In-room voice experience. Must be rendered inside a <LiveKitRoom>.
 * Owns the visualizer, agent-state readout, and the mic mute/unmute control.
 */
export default function AtlasRoom({ onLeave }: AtlasRoomProps) {
  const { state, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();

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
    <div className="flex w-full max-w-md flex-col items-center gap-8">
      {/* Plays the agent's TTS audio track automatically (no manual trigger). */}
      <RoomAudioRenderer />

      <div className="flex h-40 w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5">
        <BarVisualizer
          state={state}
          barCount={7}
          trackRef={audioTrack}
          className="h-24 w-64"
          options={{ minHeight: 8 }}
        />
      </div>

      <div className="flex items-center gap-2 text-sm font-medium text-zinc-300">
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
        {statusText}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={toggleMic}
          aria-pressed={!isMicrophoneEnabled}
          className={`flex h-12 items-center justify-center gap-2 rounded-full px-6 text-sm font-semibold transition-colors ${
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
          className="flex h-12 items-center justify-center rounded-full border border-white/20 px-6 text-sm font-semibold text-zinc-200 transition-colors hover:bg-white/10"
        >
          End session
        </button>
      </div>
    </div>
  );
}
