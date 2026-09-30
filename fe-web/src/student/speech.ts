export type SpeechView = { state: 'idle' | 'speaking' | 'paused' | 'unavailable' | 'error'; part: number; total: number; truncated: boolean };
type Voice = Pick<SpeechSynthesisVoice, 'lang' | 'localService' | 'name'>;
type Utterance = Pick<SpeechSynthesisUtterance, 'text' | 'voice' | 'lang' | 'rate' | 'onend' | 'onerror'>;
type Options = { getEpoch: () => number; voices: () => Voice[]; utterance: (text: string) => Utterance;
  speak: (value: Utterance) => void; cancel: () => void; pause: () => void; resume: () => void; changed: (view: SpeechView) => void; maxChunkMs?: number };
export const koreanLocalVoice = <T extends Voice>(voices: T[]) => voices.find(v => v.localService === true && /^ko(?:-|_|$)/i.test(v.lang));
export function speechChunks(text: string) {
  const points = Array.from(text.trim()); const bounded = points.slice(0, 10000); const chunks: string[] = [];
  for (let i = 0; i < bounded.length; i += 220) chunks.push(bounded.slice(i, i + 220).join(''));
  return { chunks, truncated: points.length > bounded.length };
}
/** Explicit local Korean voice only; one utterance at a time, with an upper bound and callback fencing. */
export function createReaderSpeech(options: Options) {
  let generation = 0; let disposed = false; let timer: ReturnType<typeof setTimeout> | undefined;
  let view: SpeechView = { state: 'idle', part: 0, total: 0, truncated: false }; let watchdog: (() => void) | null = null;
  function publish(next: SpeechView) { view = next; if (!disposed) options.changed(view); }
  function stop() { generation++; clearTimeout(timer); watchdog = null; try { options.cancel(); } catch { /* Text remains available. */ } publish({ ...view, state: 'idle', part: 0 }); }
  function fail() { stop(); publish({ ...view, state: 'error' }); }
  function start(text: string) {
    if (disposed) return; stop();
    let voice: Voice | undefined;
    try { voice = koreanLocalVoice(options.voices()); } catch { fail(); return; }
    if (!voice) { publish({ state: 'unavailable', part: 0, total: 0, truncated: false }); return; }
    const { chunks, truncated } = speechChunks(text); if (!chunks.length) return;
    const mine = generation; const epoch = options.getEpoch();
    const current = () => !disposed && mine === generation && epoch === options.getEpoch();
    function next(index: number) {
      if (!current()) return;
      if (index >= chunks.length) { clearTimeout(timer); watchdog = null; publish({ ...view, state: 'idle', part: 0 }); return; }
      try {
        const utterance = options.utterance(chunks[index]); let settled = false;
        utterance.voice = voice as SpeechSynthesisVoice; utterance.lang = voice!.lang; utterance.rate = 0.9;
        utterance.onend = () => { if (settled || !current()) return; settled = true; clearTimeout(timer); next(index + 1); };
        utterance.onerror = () => { if (settled || !current()) return; settled = true; fail(); };
        watchdog = () => { if (current() && !settled) { settled = true; fail(); } };
        publish({ state: 'speaking', part: index + 1, total: chunks.length, truncated });
        timer = setTimeout(watchdog, options.maxChunkMs ?? 60000); options.speak(utterance);
      } catch { fail(); }
    }
    next(0);
  }
  return { start, stop, getView: () => view,
    pause: () => { if (view.state === 'speaking') { try { options.pause(); clearTimeout(timer); publish({ ...view, state: 'paused' }); } catch { fail(); } } },
    resume: () => { if (view.state === 'paused') { try { options.resume(); if (watchdog) timer = setTimeout(watchdog, options.maxChunkMs ?? 60000); publish({ ...view, state: 'speaking' }); } catch { fail(); } } },
    dispose: () => { disposed = true; stop(); } };
}
