import { useCallback, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Pause, Play } from 'lucide-react';
import { cn } from './cn';

const API_BASE = import.meta.env.VITE_API_URL || '';

/** Глобальная остановка предыдущего воспроизведения (только один источник звука) */
const ttsStopAnyRef = { current: null };

/** TTS: API синтеза или fallback Web Speech API */
export function useTTSPlayback() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const synthRef = useRef(typeof window !== 'undefined' ? window.speechSynthesis : null);
  const audioRef = useRef(null);
  const isThisActiveRef = useRef(false);

  const pickVoice = useCallback(() => {
    const synth = synthRef.current;
    if (!synth) return null;
    const voices = synth.getVoices();
    const ru = voices.filter((v) => /^ru(-|_)/i.test(v.lang));
    const male = ru.find(
      (v) =>
        /male|мужск|yuri|nikolai|maxim|dmitri|aleksei|filipp|ermil|zahar/i.test(v.name) ||
        /google.*ru.*male|ru.*male|male.*ru/i.test(v.name)
    );
    return male || ru[0] || voices.find((v) => /^ru/i.test(v.lang)) || voices[0];
  }, []);

  const stop = useCallback(() => {
    ttsStopAnyRef.current = null;
    isThisActiveRef.current = false;
    synthRef.current?.cancel();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setIsSpeaking(false);
  }, []);

  const speakWeb = useCallback(
    (text) => {
      const synth = synthRef.current;
      const t = String(text || '').trim();
      if (!synth || !t) return;
      const u = new SpeechSynthesisUtterance(t);
      u.lang = 'ru-RU';
      u.rate = 0.85;
      u.volume = 1;
      u.pitch = 0.95;
      const voice = pickVoice();
      if (voice) u.voice = voice;
      u.onstart = () => {
        isThisActiveRef.current = true;
        setIsSpeaking(true);
      };
      u.onend = u.onerror = () => {
        if (isThisActiveRef.current) setIsSpeaking(false);
        isThisActiveRef.current = false;
      };
      synth.speak(u);
    },
    [pickVoice]
  );

  const speak = useCallback(
    async (text) => {
      const t = String(text || '').trim();
      if (!t) return;
      ttsStopAnyRef.current?.();
      ttsStopAnyRef.current = stop;

      setIsLoading(true);
      const apiUrl = API_BASE ? `${API_BASE.replace(/\/$/, '')}/api/tts/synthesize` : '/api/tts/synthesize';
      try {
        const r = await fetch(apiUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: t }),
        });
        if (r.ok) {
          const blob = await r.blob();
          const ct = r.headers.get('content-type') || '';
          if (!ct.includes('audio') && blob.size < 100) {
            speakWeb(t);
            return;
          }
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          audioRef.current = audio;
          audio.onended = () => {
            URL.revokeObjectURL(url);
            if (isThisActiveRef.current) setIsSpeaking(false);
            isThisActiveRef.current = false;
          };
          audio.onerror = () => {
            URL.revokeObjectURL(url);
            if (isThisActiveRef.current) speakWeb(t);
            setIsSpeaking(false);
          };
          isThisActiveRef.current = true;
          setIsSpeaking(true);
          try {
            await audio.play();
          } catch {
            URL.revokeObjectURL(url);
            speakWeb(t);
          }
        } else {
          speakWeb(t);
        }
      } catch {
        speakWeb(t);
      }
      setIsLoading(false);
    },
    [stop, speakWeb]
  );

  const toggle = useCallback(
    (utterance) => {
      if (isSpeaking || isLoading) {
        stop();
      } else {
        speak(utterance);
      }
    },
    [isSpeaking, isLoading, speak, stop]
  );

  return { speak, stop, toggle, isSpeaking, isLoading };
}

export function TtsPlayButton({ text, className = '', circleClassName }) {
  const { toggle, isSpeaking, isLoading } = useTTSPlayback();
  const t = String(text || '').trim();
  if (!t) return null;
  const circle = circleClassName ?? 'w-[38px] h-[38px]';
  return (
    <motion.button
      type="button"
      onClick={() => toggle(text)}
      aria-label={isSpeaking || isLoading ? 'Остановить' : 'Слушать'}
      className={cn(
        circle,
        'relative rounded-full flex items-center justify-center shrink-0 overflow-hidden',
        'border-2 border-amber-400/50 bg-amber-400/15 text-amber-200',
        'hover:bg-amber-400/25 hover:border-amber-400/70 transition-colors',
        className
      )}
    >
      {isLoading ? (
        <motion.svg viewBox="0 0 48 48" className="absolute inset-0 h-full w-full" aria-hidden>
          <circle cx="24" cy="24" r="20" fill="none" stroke="rgba(251,191,36,0.2)" strokeWidth="2.5" />
          <motion.circle
            key="tts-progress"
            cx="24"
            cy="24"
            r="20"
            fill="none"
            stroke="rgba(251,191,36,0.95)"
            strokeWidth="2.5"
            strokeLinecap="round"
            initial={{ pathLength: 0.02 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 7, ease: 'linear' }}
            style={{ rotate: -90, transformOrigin: '50% 50%' }}
          />
        </motion.svg>
      ) : null}
      {isSpeaking ? <Pause className="w-[18px] h-[18px]" strokeWidth={2} /> : <Play className="w-[18px] h-[18px] ml-0.5" strokeWidth={2} />}
    </motion.button>
  );
}
