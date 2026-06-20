"use client";

import { useEffect, useRef } from "react";
import {
  useLocalParticipant,
  useTranscriptions,
} from "@livekit/components-react";

/**
 * Live chat transcript. Renders STT (user) and TTS (Atlas) transcriptions as
 * modern chat bubbles, distinguishing speakers by participant identity.
 */
export default function Transcript() {
  const transcriptions = useTranscriptions();
  const { localParticipant } = useLocalParticipant();
  const localIdentity = localParticipant?.identity;

  const bottomRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view as the conversation grows.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcriptions.length]);

  if (transcriptions.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-zinc-500">
        Your conversation with Atlas will appear here. Try saying
        <br />
        <span className="text-zinc-300">
          “I want a mid-range beach trip.”
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto px-4 py-4">
      {transcriptions.map((t, idx) => {
        const isUser = t.participantInfo?.identity === localIdentity;
        return (
          <div
            key={t.streamInfo?.id ?? `${idx}-${t.text.slice(0, 8)}`}
            className={`flex ${isUser ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
                isUser
                  ? "rounded-br-sm bg-sky-600 text-white"
                  : "rounded-bl-sm bg-zinc-800 text-zinc-100"
              }`}
            >
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide opacity-60">
                {isUser ? "You" : "Atlas"}
              </span>
              {t.text}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
