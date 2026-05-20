import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

import { getMagic8BallAnswers } from '../../data/magic8BallAnswers';

/**
 * Состояние и логика шара предсказаний. Вынесено в отдельный модуль без Three.js,
 * чтобы при ошибке загрузки 3D-шара в Profile показывать лайт-модалку с тем же состоянием.
 */
export function useMagic8BallState(open, onClose) {
  const [answer, setAnswer] = useState(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const [hasResult, setHasResult] = useState(false);
  const [sceneKey, setSceneKey] = useState(0);
  const timeoutRef = useRef(null);
  const resetTimeoutRef = useRef(null);
  const finishTimeoutRef = useRef(null);
  const lastIndexRef = useRef(-1);

  const resetBall = useCallback((resetScene = false) => {
    window.clearTimeout(timeoutRef.current);
    window.clearTimeout(resetTimeoutRef.current);
    window.clearTimeout(finishTimeoutRef.current);
    timeoutRef.current = null;
    resetTimeoutRef.current = null;
    finishTimeoutRef.current = null;
    if (!resetScene && hasResult && answer) {
      // Step 1: hide prediction text, keep smooth scale-back animation.
      setAnswer('');
      setHasResult(false);
      setIsAnimating(false);
      // Step 2: after shrink settles, return to default "Узнай".
      resetTimeoutRef.current = window.setTimeout(() => {
        setAnswer(null);
        resetTimeoutRef.current = null;
      }, 560);
      return;
    }
    setAnswer(null);
    setHasResult(false);
    setIsAnimating(false);
    if (resetScene) setSceneKey((k) => k + 1);
  }, [answer, hasResult]);

  const getRandomAnswer = useCallback(() => {
    const answers = getMagic8BallAnswers();
    if (!Array.isArray(answers) || answers.length === 0) return 'Спроси снова';
    let index = Math.floor(Math.random() * answers.length);
    if (answers.length > 1) {
      while (index === lastIndexRef.current) {
        index = Math.floor(Math.random() * answers.length);
      }
    }
    lastIndexRef.current = index;
    return answers[index];
  }, []);

  const triggerPrediction = useCallback((delayMs = 900) => {
    if (isAnimating || !open) return;
    window.clearTimeout(timeoutRef.current);
    window.clearTimeout(finishTimeoutRef.current);
    timeoutRef.current = null;
    finishTimeoutRef.current = null;
    setIsAnimating(true);
    setHasResult(false);
    setAnswer(null);
    const tg = window?.Telegram?.WebApp;
    if (tg?.HapticFeedback?.impactOccurred) {
      try { tg.HapticFeedback.impactOccurred('medium'); } catch (_) {}
    } else if (navigator?.vibrate) {
      navigator.vibrate(70);
    }
    const nextAnswer = getRandomAnswer();
    const revealDelay = Math.max(1100, Math.floor(delayMs * 0.55));
    timeoutRef.current = window.setTimeout(() => {
      setAnswer(nextAnswer);
      timeoutRef.current = null;
    }, revealDelay);
    finishTimeoutRef.current = window.setTimeout(() => {
      setHasResult(true);
      setIsAnimating(false);
      finishTimeoutRef.current = null;
    }, delayMs);
  }, [getRandomAnswer, isAnimating, open]);

  useEffect(() => {
    return () => {
      window.clearTimeout(timeoutRef.current);
      window.clearTimeout(resetTimeoutRef.current);
      window.clearTimeout(finishTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (!open) resetBall(true);
  }, [open, resetBall]);

  return {
    answer,
    isAnimating,
    hasResult,
    triggerPrediction,
    resetBall,
    sceneKey,
  };
}

/**
 * Упрощённая модалка шара без WebGL. Используется как fallback при ошибке загрузки 3D.
 */
export function Magic8BallLiteModal({
  onClose,
  answer,
  isAnimating,
  hasResult,
  triggerPrediction,
  resetBall,
  secondaryAction = null,
}) {
  const handlePrimaryAction = () => {
    if (isAnimating) return;
    triggerPrediction(3000);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.22 }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'transparent',
        backdropFilter: 'none',
        WebkitBackdropFilter: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 8,
      }}
    >
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        style={{
          position: 'relative',
          width: 'min(980px, 100%)',
          minHeight: 'min(430px, 72vh)',
          borderRadius: 28,
          overflow: 'visible',
          background: 'linear-gradient(180deg, rgba(18,22,32,0.64) 0%, rgba(10,13,20,0.68) 100%)',
          border: '1px solid rgba(145, 168, 255, 0.12)',
          backdropFilter: 'blur(16px) saturate(115%)',
          WebkitBackdropFilter: 'blur(16px) saturate(115%)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <button
          type="button"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 14,
            right: 14,
            zIndex: 3,
            width: 44,
            height: 44,
            borderRadius: 999,
            border: '1px solid rgba(255,255,255,0.1)',
            background: 'rgba(255,255,255,0.05)',
            color: '#e8ecff',
            fontSize: 24,
            cursor: 'pointer',
          }}
          aria-label="Закрыть"
        >
          ×
        </button>
        <div
          style={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 14px 0',
          }}
        >
          <div
            style={{
              width: 'min(88vw, 320px)',
              aspectRatio: '1 / 1',
              maxHeight: '50vh',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                width: '100%',
                height: '100%',
                borderRadius: '50%',
                background: 'radial-gradient(circle at 35% 30%, #2a2e38, #1a1e25 50%, #0c0f14)',
                boxShadow: 'inset -8px -8px 24px rgba(0,0,0,0.5), inset 8px 8px 24px rgba(255,255,255,0.04), 0 20px 40px rgba(0,0,0,0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: isAnimating ? 'default' : 'pointer',
              }}
              onClick={() => !isAnimating && triggerPrediction()}
              onKeyDown={(e) => e.key === 'Enter' && !isAnimating && triggerPrediction()}
              role="button"
              tabIndex={0}
              aria-label="Спросить шар"
            >
              <div
                style={{
                  width: '42%',
                  height: '42%',
                  borderRadius: '50%',
                  background: 'linear-gradient(180deg, #2f79ff 0%, #1b53ff 50%, #1532d8 100%)',
                  boxShadow: 'inset 0 0 20px rgba(47,121,255,0.4), 0 0 30px rgba(27,83,255,0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: 8,
                  boxSizing: 'border-box',
                }}
              >
                <span
                  style={{
                    fontSize: 'clamp(10px, 2.8vw, 14px)',
                    fontWeight: 700,
                    color: 'rgba(247,249,255,0.98)',
                    textAlign: 'center',
                    lineHeight: 1.25,
                    fontFamily: "'Bion', sans-serif",
                    wordBreak: 'break-word',
                  }}
                >
                  {isAnimating ? '...' : (answer ?? 'Узнай')}
                </span>
              </div>
            </div>
          </div>
        </div>
        <div
          style={{
            padding: '0 12px 14px',
            marginTop: 0,
            transform: 'translateY(-20%)',
            display: 'flex',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              maxWidth: 680,
              textAlign: 'center',
              color: '#dfe6ff',
              fontFamily: "'Bion', sans-serif",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>Задайте вопрос в форме,</div>
            <div style={{ marginTop: 2, fontSize: 12, opacity: 0.85 }}>предполагающей ответ &quot;Да&quot; или &quot;Нет&quot;</div>
            <button
              type="button"
              onClick={handlePrimaryAction}
              disabled={isAnimating}
              style={{
                marginTop: 8,
                minWidth: 178,
                maxWidth: 360,
                height: 62,
                borderRadius: 14,
                border: hasResult
                  ? '1px solid rgba(136,164,255,0.42)'
                  : '1px solid rgba(186,196,225,0.4)',
                background: hasResult
                  ? 'linear-gradient(180deg, rgba(72,110,255,0.46), rgba(35,63,156,0.5))'
                  : 'linear-gradient(180deg, rgba(123,136,168,0.38), rgba(80,89,114,0.44))',
                boxShadow: hasResult
                  ? '0 8px 20px rgba(23, 52, 162, 0.34), inset 0 1px 0 rgba(255,255,255,0.18)'
                  : '0 8px 20px rgba(14, 19, 38, 0.36), inset 0 1px 0 rgba(255,255,255,0.18)',
                color: '#f4f7ff',
                fontWeight: 700,
                fontSize: 13,
                cursor: isAnimating ? 'not-allowed' : 'pointer',
                opacity: isAnimating ? 0.65 : 1,
                fontFamily: "'Bion', sans-serif",
              }}
            >
              Получить ответ
            </button>
            {secondaryAction?.label && secondaryAction?.onClick ? (
              <button
                type="button"
                onClick={secondaryAction.onClick}
                disabled={isAnimating}
                style={{
                  marginTop: 10,
                  minWidth: 178,
                  maxWidth: 360,
                  width: '100%',
                  height: 62,
                  borderRadius: 14,
                  border: hasResult
                    ? '1px solid rgba(136,164,255,0.42)'
                    : '1px solid rgba(186,196,225,0.4)',
                  background: hasResult
                    ? 'linear-gradient(180deg, rgba(72,110,255,0.46), rgba(35,63,156,0.5))'
                    : 'linear-gradient(180deg, rgba(123,136,168,0.38), rgba(80,89,114,0.44))',
                  boxShadow: hasResult
                    ? '0 8px 20px rgba(23, 52, 162, 0.34), inset 0 1px 0 rgba(255,255,255,0.18)'
                    : '0 8px 20px rgba(14, 19, 38, 0.36), inset 0 1px 0 rgba(255,255,255,0.18)',
                  color: '#f4f7ff',
                  fontWeight: 700,
                  fontSize: 13,
                  cursor: isAnimating ? 'not-allowed' : 'pointer',
                  opacity: isAnimating ? 0.65 : 1,
                  fontFamily: "'Bion', sans-serif",
                }}
              >
                {secondaryAction.label}
              </button>
            ) : null}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
