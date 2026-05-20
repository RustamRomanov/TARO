import { lazy, Suspense } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import ErrorBoundary from '../ErrorBoundary';
import { useMagic8BallState, Magic8BallLiteModal } from '../magic8ball/Magic8BallShared';

const Magic8Ball = lazy(() => import('../magic8ball/Magic8Ball'));

function MagicBallScenePlaceholder() {
  return (
    <div
      className="mx-auto w-full max-w-[min(1220px,104vw)] aspect-square max-h-[58vh] min-h-[min(58vh,100vw)] shrink-0"
      aria-hidden
    />
  );
}

export default function TarotMagicBallOverlay({ open, onClose }) {
  const ballState = useMagic8BallState(open, onClose);

  if (typeof document === 'undefined') return null;

  const titleStyle = {
    fontFamily: "'Cormorant Garamond', Georgia, 'Times New Roman', serif",
    fontWeight: 400,
    fontSynthesis: 'none',
    fontSize: '24px',
    lineHeight: 1.15,
    letterSpacing: '0.08em',
    color: '#ffffff',
    textShadow: '0 1px 2px rgba(0,0,0,0.45), 0 0 10px rgba(255,255,255,0.25)',
    WebkitTextSizeAdjust: '100%',
    textSizeAdjust: '100%',
  };

  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div
          key="tarot-magic-ball"
          className="fixed inset-0 z-[99990] flex flex-col w-full overflow-hidden bg-[#0e090c]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          style={{
            paddingTop: 'calc(max(48px, env(safe-area-inset-top, 0px)) + 2px + 12%)',
            paddingBottom: 'max(env(safe-area-inset-bottom, 0px), constant(safe-area-inset-bottom))',
            overscrollBehavior: 'none',
          }}
        >
          <h1
            className="text-center mb-2 uppercase leading-tight [&_span]:block font-normal shrink-0 pointer-events-none"
            style={titleStyle}
          >
            <span>Магический</span>
            <span>шар</span>
            <span>предсказаний</span>
          </h1>

          <div className="flex flex-1 flex-col min-h-0 w-full justify-center -mt-2">
            <Suspense fallback={<MagicBallScenePlaceholder />}>
              <ErrorBoundary
                fallback={
                  <Magic8BallLiteModal
                    onClose={onClose}
                    answer={ballState.answer}
                    isAnimating={ballState.isAnimating}
                    hasResult={ballState.hasResult}
                    triggerPrediction={ballState.triggerPrediction}
                    resetBall={ballState.resetBall}
                    secondaryAction={{ label: 'Вернуться в ТАРО', onClick: onClose }}
                  />
                }
              >
                <motion.div
                  className="flex flex-1 flex-col min-h-0 w-full justify-center"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                  style={{ touchAction: 'none' }}
                >
                  <Magic8Ball
                    variant="page"
                    open
                    onClose={onClose}
                    answer={ballState.answer}
                    isAnimating={ballState.isAnimating}
                    hasResult={ballState.hasResult}
                    triggerPrediction={ballState.triggerPrediction}
                    resetBall={ballState.resetBall}
                    sceneKey={ballState.sceneKey}
                    secondaryAction={{ label: 'Вернуться в ТАРО', onClick: onClose }}
                  />
                </motion.div>
              </ErrorBoundary>
            </Suspense>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
