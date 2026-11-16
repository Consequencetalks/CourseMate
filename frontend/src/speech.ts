import { renderMarkdown } from "./markdown";

const TARGET_RATE = 16000;
const MAX_LISTEN_MS = 60_000;

export type RecognitionHandlers = {
  onText: (text: string) => void;
  onError: (message: string) => void;
  onEnd: (finalText: string) => void;
};

type ListenSession = {
  stop: () => void;
  cancel: () => void;
};

type SpeechSession = {
  generation: number;
  controller: AbortController;
  queue: string[];
  pending: Promise<Blob> | null;
  pumping: boolean;
  closed: boolean;
  failed: boolean;
  releasePlay: (() => void) | null;
};

let active: ListenSession | null = null;
let speakGeneration = 0;
let speakController: AbortController | null = null;
let currentAudio: HTMLAudioElement | null = null;
let speechSession: SpeechSession | null = null;
let liveRawEnd = 0;
let reportError: (message: string) => void = () => undefined;

export function onSpeechError(handler: (message: string) => void): void {
  reportError = handler;
}

export function recognitionSupported(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function";
}

export function toSpeechText(source: string): string {
  const cleaned = source.replace(/\s*\[S\d+\]/g, "");
  const holder = document.createElement("div");
  holder.innerHTML = renderMarkdown(cleaned);
  const text = holder.innerText || holder.textContent || "";
  return text.replace(/\s+/g, " ").trim();
}

export function cancelRecognition(): void {
  active?.cancel();
  active = null;
}

export function finishRecognition(): void {
  active?.stop();
}

export function startRecognition(handlers: RecognitionHandlers): void {
  cancelRecognition();
  if (!recognitionSupported()) {
    handlers.onError("Voice input needs a browser microphone.");
    handlers.onEnd("");
    return;
  }
  const state = { closed: false, accepted: true };
  const queued: string[] = [];
  let socket: WebSocket | null = null;
  let context: AudioContext | null = null;
  let stream: MediaStream | null = null;
  let timer = 0;

  const cleanup = () => {
    if (state.closed) {
      return;
    }
    state.closed = true;
    window.clearTimeout(timer);
    socket?.close();
    stream?.getTracks().forEach((track) => track.stop());
    void context?.close();
    if (active === session) {
      active = null;
    }
  };
  const fail = (message: string) => {
    if (!state.accepted || state.closed) {
      return;
    }
    state.accepted = false;
    cleanup();
    handlers.onError(message);
    handlers.onEnd("");
  };
  const session: ListenSession = {
    stop() {
      if (state.closed) {
        return;
      }
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop" }));
        return;
      }
      state.accepted = false;
      cleanup();
      handlers.onEnd("");
    },
    cancel() {
      state.accepted = false;
      cleanup();
    },
  };
  active = session;

  void navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then(async (media) => {
      if (!state.accepted) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = media;
      context = new AudioContext();
      await context.resume();
      const source = context.createMediaStreamSource(media);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silent = context.createGain();
      silent.gain.value = 0;
      const sendPcm = (pcm: string) => {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "audio", pcm }));
          return;
        }
        if (queued.length < 200) {
          queued.push(pcm);
        }
      };
      processor.onaudioprocess = (event) => {
        if (!state.accepted) {
          return;
        }
        const samples = downsample(event.inputBuffer.getChannelData(0), context?.sampleRate ?? TARGET_RATE);
        if (!samples.length) {
          return;
        }
        sendPcm(bytesToBase64(samples));
      };
      source.connect(processor);
      processor.connect(silent);
      silent.connect(context.destination);
      socket = new WebSocket(speechSocketUrl());
      socket.onopen = () => {
        if (!state.accepted || socket?.readyState !== WebSocket.OPEN) {
          return;
        }
        for (const pcm of queued) {
          socket.send(JSON.stringify({ type: "audio", pcm }));
        }
        queued.length = 0;
      };
      socket.onmessage = (event) => {
        if (!state.accepted) {
          return;
        }
        const message = parseMessage(event.data);
        if (!message) {
          return;
        }
        if (message.type === "partial" && message.text) {
          handlers.onText(message.text);
        } else if (message.type === "final") {
          state.accepted = false;
          cleanup();
          handlers.onEnd(message.text);
        } else if (message.type === "error") {
          fail(message.text || "Voice recognition failed.");
        }
      };
      socket.onerror = () => fail("Voice recognition failed.");
      socket.onclose = () => {
        if (state.accepted && !state.closed) {
          fail("Voice recognition ended before it finished.");
        }
      };
      timer = window.setTimeout(() => session.stop(), MAX_LISTEN_MS);
    })
    .catch(() => fail("Microphone permission was blocked."));
}

export function stopSpeaking(): void {
  speakGeneration += 1;
  const current = speechSession;
  speechSession = null;
  liveRawEnd = 0;
  speakController?.abort();
  speakController = null;
  current?.releasePlay?.();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
}

export function pushLiveSpeech(raw: string): void {
  if (!speechSession || speechSession.generation !== speakGeneration) {
    openSession();
  }
  const current = speechSession;
  if (!current || current.closed || raw.length < liveRawEnd) {
    return;
  }
  const ready = splitReady(raw.slice(liveRawEnd));
  if (!ready.consumed) {
    return;
  }
  liveRawEnd += ready.consumed;
  current.queue.push(...ready.pieces);
  if (ready.pieces.length) {
    void pump(current);
  }
}

export function finishLiveSpeech(raw: string): void {
  const current = speechSession;
  if (!current || current.generation !== speakGeneration || current.closed) {
    return;
  }
  const rest = raw.slice(liveRawEnd);
  liveRawEnd = raw.length;
  current.queue.push(...sentencesOf(rest));
  current.closed = true;
  void pump(current);
}

export async function speak(source: string): Promise<void> {
  const current = openSession();
  const pieces = sentencesOf(toSpeechText(source));
  if (!pieces.length) {
    return;
  }
  current.queue.push(...pieces);
  current.closed = true;
  await pump(current);
}

function openSession(): SpeechSession {
  stopSpeaking();
  const controller = new AbortController();
  speakController = controller;
  const current: SpeechSession = {
    generation: speakGeneration,
    controller,
    queue: [],
    pending: null,
    pumping: false,
    closed: false,
    failed: false,
    releasePlay: null,
  };
  speechSession = current;
  return current;
}

function splitReady(text: string): { pieces: string[]; consumed: number } {
  const pieces: string[] = [];
  let consumed = 0;
  let rest = text;
  while (rest) {
    const cut = firstBoundary(rest);
    if (cut <= 0) {
      break;
    }
    const spoken = toSpeechText(rest.slice(0, cut));
    if (spoken) {
      pieces.push(spoken);
    }
    consumed += cut;
    rest = rest.slice(cut);
  }
  return { pieces, consumed };
}

function sentencesOf(text: string): string[] {
  const ready = splitReady(text);
  const pieces = [...ready.pieces];
  const tail = toSpeechText(text.slice(ready.consumed));
  if (tail) {
    pieces.push(tail);
  }
  return pieces;
}

function firstBoundary(text: string): number {
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const chinese = "。！？；;\n".includes(char);
    const western = char === "." || char === "!" || char === "?";
    if (!chinese && !western) {
      continue;
    }
    if (western) {
      const previous = text[index - 1] ?? "";
      const next = text[index + 1];
      if (/\d/.test(previous) || (next !== undefined && !/\s/.test(next))) {
        continue;
      }
    }
    let cursor = index + 1;
    while (cursor < text.length && /\s/.test(text[cursor])) {
      cursor += 1;
    }
    return cursor;
  }
  return 0;
}

async function pump(current: SpeechSession): Promise<void> {
  if (current.pumping || current.failed) {
    return;
  }
  current.pumping = true;
  let started = false;
  try {
    while (current.generation === speakGeneration && !current.failed) {
      if (!current.pending && current.queue.length) {
        current.pending = fetchAudio(takeBatch(current.queue, !started), current);
      }
      if (!current.pending) {
        if (current.closed) {
          break;
        }
        return;
      }
      const blob = await current.pending;
      current.pending = null;
      if (current.generation !== speakGeneration || current.failed) {
        return;
      }
      started = true;
      if (current.queue.length) {
        current.pending = fetchAudio(takeBatch(current.queue, false), current);
      }
      await playBlob(blob, current);
    }
  } catch (error) {
    if (current.generation !== speakGeneration || current.controller.signal.aborted) {
      return;
    }
    current.failed = true;
    const aborted = error instanceof DOMException && error.name === "AbortError";
    if (!aborted) {
      reportError(error instanceof Error ? error.message : "Could not read the answer.");
    }
  } finally {
    current.pumping = false;
    if (
      current === speechSession &&
      current.generation === speakGeneration &&
      !current.failed &&
      (current.queue.length > 0 || current.pending !== null)
    ) {
      void pump(current);
    }
  }
}

function takeBatch(queue: string[], first: boolean): string {
  const limit = 480;
  let batch = "";
  while (queue.length) {
    const next = queue[0];
    if (batch && (first || batch.length + 1 + next.length > limit)) {
      break;
    }
    queue.shift();
    batch = batch ? `${batch} ${next}` : next;
    if (first) {
      break;
    }
  }
  return batch;
}

async function fetchAudio(text: string, current: SpeechSession): Promise<Blob> {
  const response = await fetch("/api/speech/synthesize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal: current.controller.signal,
  });
  if (!response.ok) {
    throw new Error("Could not read the answer.");
  }
  return response.blob();
}

function playBlob(blob: Blob, current: SpeechSession): Promise<void> {
  return new Promise((resolve, reject) => {
    if (current.generation !== speakGeneration) {
      resolve();
      return;
    }
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    let settled = false;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      URL.revokeObjectURL(url);
      if (currentAudio === audio) {
        currentAudio = null;
      }
      if (current.releasePlay === finish) {
        current.releasePlay = null;
      }
      resolve();
    };
    current.releasePlay = finish;
    audio.onended = finish;
    audio.onerror = () => {
      if (!settled) {
        settled = true;
        URL.revokeObjectURL(url);
        reject(new Error("Could not play the answer."));
      }
    };
    void audio.play().catch((error: unknown) => {
      if (!settled) {
        settled = true;
        URL.revokeObjectURL(url);
        reject(error instanceof Error ? error : new Error("Could not play the answer."));
      }
    });
  });
}

function speechSocketUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/speech/transcribe`;
}

function parseMessage(data: unknown): { type: string; text: string } | null {
  if (typeof data !== "string") {
    return null;
  }
  try {
    const payload = JSON.parse(data) as { type?: unknown; text?: unknown };
    if (typeof payload.type !== "string") {
      return null;
    }
    return { type: payload.type, text: typeof payload.text === "string" ? payload.text : "" };
  } catch {
    return null;
  }
}

function downsample(input: Float32Array, fromRate: number): Uint8Array {
  const ratio = fromRate / TARGET_RATE;
  const length = Math.max(1, Math.floor(input.length / ratio));
  const bytes = new Uint8Array(length * 2);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(input.length, Math.floor((index + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let sample = start; sample < end; sample += 1) {
      sum += input[sample];
      count += 1;
    }
    const value = Math.max(-1, Math.min(1, count ? sum / count : 0));
    view.setInt16(index * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const step = 0x8000;
  for (let index = 0; index < bytes.length; index += step) {
    binary += String.fromCharCode(...bytes.subarray(index, index + step));
  }
  return btoa(binary);
}
