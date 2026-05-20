import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '../lib/cn';

const WORD = 'TARO'.split('');

export default function SplashIntro() {
  const [phase, setPhase] = useState('intro'); // intro -> scatter -> done
  const stars = useMemo(
    () => Array.from({ length: 24 }).map((_, i) => ({
      id: i,
      top: `${12 + ((i * 17) % 72)}%`,
      left: `${8 + ((i * 29) % 84)}%`,
      size: 1 + (i % 3),
      delay: i * 0.12,
    })),
    []
  );

  const letterOffsets = useMemo(
    () =>
      WORD.map((_, i) => ({
        x: ((i % 2 === 0 ? -1 : 1) * (8 + (i * 3))),
        y: (i % 3 === 0 ? -1 : 1) * (4 + i),
        r: (i % 2 === 0 ? -1 : 1) * (3 + i),
      })),
    []
  );

  useEffect(() => {
    const t1 = setTimeout(() => setPhase('scatter'), 2200);  // распадание букв на 0.8 сек раньше (было 3 сек)
    const t2 = setTimeout(() => setPhase('done'), 3000);      // выход из темноты
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  return (
    <AnimatePresence>
      {phase !== 'done' && (
        <motion.div
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.2, ease: [0.4, 0, 0.2, 1] }}
          className="fixed inset-0 z-[90] bg-black flex items-center justify-center pointer-events-none"
        >
          {stars.map((s) => (
            <motion.span
              key={s.id}
              className="absolute rounded-full bg-amber-300/80"
              style={{ top: s.top, left: s.left, width: s.size, height: s.size }}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: [0.5, 0.9, 0.5], scale: [0.9, 1.15, 1] }}
              transition={{
                opacity: { duration: 2.5, repeat: Infinity, delay: s.delay, ease: 'easeInOut' },
                scale: { duration: 2.5, repeat: Infinity, delay: s.delay, ease: 'easeInOut' },
              }}
            />
          ))}
          <div className="relative overflow-visible">
            <div className="flex items-center justify-center gap-0.5">
              {WORD.map((ch, i) => (
                <motion.span
                  key={`${ch}-${i}`}
                  className={cn('font-cinzel text-xl tracking-[0.2em] block', phase !== 'scatter' && 'astrov-shine')}
                  style={{
                    background: 'linear-gradient(90deg, #d4a017 0%, #d4a017 38%, #fcd34d 50%, #d4a017 62%, #d4a017 100%)',
                    backgroundSize: '220% 100%',
                    WebkitBackgroundClip: 'text',
                    backgroundClip: 'text',
                    color: 'transparent',
                  }}
                  initial={{ opacity: 0, scale: 0.55 }}
                  animate={
                    phase === 'scatter'
                      ? {
                          opacity: 0,
                          scale: 1.4,
                          x: letterOffsets[i].x,
                          y: letterOffsets[i].y,
                          rotate: letterOffsets[i].r,
                          filter: 'blur(3px)',
                        }
                      : {
                          opacity: 1,
                          scale: [1, 1.4],
                          filter: 'blur(0px)',
                        }
                  }
                  transition={{
                    duration: phase === 'scatter' ? 0.9 : 3.5,
                    delay: phase === 'scatter' ? i * 0.03 : 0.08 + i * 0.1,
                    ease: 'easeOut',
                  }}
                >
                  {ch}
                </motion.span>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

