import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/cn';

const SCALE_SELECTED_DEFAULT = 1.2;

function useChaoticLevitateParams(n) {
  return useMemo(
    () =>
      Array.from({ length: n }, (_, i) => {
        const amp = 0.75 + Math.random() * 1.5;
        const dur = 5.5 + Math.random() * 0.8;
        const delay = Math.random() * 1.5;
        const phase = (i / n) * Math.PI * 2 + Math.random() * 0.3;
        return { amp, dur, delay, phase };
      }),
    [n]
  );
}

/** Круговая траектория: 24 точки для плавной левитации. amp - радиус, phase - смещение в радианах. */
function getCircularKeyframes(amp, phase = 0) {
  const pts = 60;
  const x = [];
  const y = [];
  for (let i = 0; i <= pts; i++) {
    const a = phase + (i / pts) * Math.PI * 2;
    x.push(Math.cos(a) * amp);
    y.push(Math.sin(a) * amp);
  }
  return { x, y };
}

/**
 * Простой горизонтальный скролл: свайп, выбор по нажатию.
 * scaleSelected/scaleUnselected, levitate, levitateChaotic, swayPx.
 */
export default function SimpleSwipePicker({
  items = [],
  selectedId,
  onSelect,
  renderItem,
  itemWidth,
  itemHeight,
  gap = 12,
  className,
  levitate = false,
  levitateChaotic = false,
  swayPx = 0,
  scaleSelected = SCALE_SELECTED_DEFAULT,
  scaleUnselected = 1,
  overflowVisible = false,
  overlapPx = 0,
  edgePadding = 0,
  selectByCenter = false,
  hapticOnCenterSelect = false,
  useDistanceScaling = false,
  immediateNeighborScale = 0.8,
  immediateNeighborDistanceFactor = 1,
  secondNeighborScale = 0.64,
  secondNeighborPullPx = 10,
  secondNeighborDistanceFactor = 1,
}) {
  const scrollRef = useRef(null);
  const rafRef = useRef(null);
  const lastCenterIdRef = useRef(selectedId || '');
  const lastHapticMsRef = useRef(0);

  useEffect(() => {
    lastCenterIdRef.current = selectedId || '';
  }, [selectedId]);

  const fireLightHaptic = useCallback(() => {
    const now = Date.now();
    if (now - lastHapticMsRef.current < 90) return;
    lastHapticMsRef.current = now;
    try {
      const tg = window?.Telegram?.WebApp;
      if (tg?.HapticFeedback?.impactOccurred) {
        tg.HapticFeedback.impactOccurred('light');
        return;
      }
    } catch (_) {}
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      navigator.vibrate(10);
    }
  }, []);

  const updateCenterAndSelection = useCallback(() => {
    if (!selectByCenter || !onSelect) return;
    const el = scrollRef.current;
    if (!el) return;
    if (!items.length) return;
    const pitch = itemWidth + gap + overlapPx;
    if (pitch <= 0) return;
    const centerX = el.scrollLeft + el.clientWidth / 2;
    const firstCenter = edgePadding + itemWidth / 2;
    const rawIdx = Math.round((centerX - firstCenter) / pitch);
    const idx = Math.max(0, Math.min(items.length - 1, rawIdx));
    const closestId = items[idx]?.id;
    if (!closestId || closestId === selectedId) return;
    if (hapticOnCenterSelect && closestId !== lastCenterIdRef.current) {
      fireLightHaptic();
    }
    lastCenterIdRef.current = closestId;
    onSelect(closestId);
  }, [
    items,
    selectedId,
    onSelect,
    selectByCenter,
    itemWidth,
    gap,
    overlapPx,
    edgePadding,
    hapticOnCenterSelect,
    fireLightHaptic,
  ]);

  useEffect(() => {
    if (!selectByCenter) return;
    const el = scrollRef.current;
    if (!el) return;
    updateCenterAndSelection();
    const ro = new ResizeObserver(updateCenterAndSelection);
    ro.observe(el);
    const onScroll = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(updateCenterAndSelection);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', updateCenterAndSelection);
    return () => {
      ro.disconnect();
      el.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', updateCenterAndSelection);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [updateCenterAndSelection, selectByCenter, items]);

  const baseW = itemWidth;
  const baseH = itemHeight;
  const scaleSel = scaleSelected;
  const scaleUn = scaleUnselected;
  const selectedIndex = useMemo(() => {
    const idx = items.findIndex((item) => item.id === selectedId);
    if (idx >= 0) return idx;
    return items.length > 0 ? 0 : -1;
  }, [items, selectedId]);
  const levitateParams = useChaoticLevitateParams(items.length);
  const levitateMotionByIndex = useMemo(
    () => items.map((_, i) => {
      if (!levitate) return { x: 0, y: 0 };
      if (levitateChaotic && levitateParams[i]) {
        const { amp, phase } = levitateParams[i];
        const kf = getCircularKeyframes(amp, phase);
        return { x: kf.x, y: kf.y };
      }
      const kf = getCircularKeyframes(1);
      return { x: kf.x, y: kf.y };
    }),
    [items, levitate, levitateChaotic, levitateParams]
  );

  const getDistanceScale = useCallback((i, isSelected) => {
    if (!useDistanceScaling || selectedIndex < 0) return isSelected ? scaleSel : scaleUn;
    const dist = Math.abs(i - selectedIndex);
    if (dist === 0) return scaleSel;
    if (dist === 1) return scaleSel * immediateNeighborScale;
    if (dist === 2) return scaleSel * secondNeighborScale;
    return scaleUn;
  }, [
    useDistanceScaling,
    selectedIndex,
    scaleSel,
    scaleUn,
    immediateNeighborScale,
    secondNeighborScale,
  ]);

  const getCenterPullPx = useCallback((i) => {
    if (!useDistanceScaling || selectedIndex < 0) return 0;
    const dist = Math.abs(i - selectedIndex);
    if (dist !== 1 && dist !== 2) return 0;
    const directionToCenter = i < selectedIndex ? 1 : -1;
    const pitch = itemWidth + gap + overlapPx;
    if (dist === 1) {
      const immediateFactor = Math.max(0, Math.min(1, Number(immediateNeighborDistanceFactor) || 1));
      const immediatePull = pitch * (1 - immediateFactor);
      return directionToCenter * immediatePull;
    }
    const secondFactor = Math.max(0, Math.min(1, Number(secondNeighborDistanceFactor) || 1));
    const secondPull = pitch * (1 - secondFactor);
    return directionToCenter * (secondNeighborPullPx + secondPull);
  }, [
    useDistanceScaling,
    selectedIndex,
    immediateNeighborDistanceFactor,
    secondNeighborPullPx,
    secondNeighborDistanceFactor,
    itemWidth,
    gap,
    overlapPx,
  ]);

  const withCenterPull = useCallback((xMotion, pullPx) => {
    if (!pullPx) return xMotion;
    if (Array.isArray(xMotion)) return xMotion.map((x) => x + pullPx);
    if (typeof xMotion === 'number') return xMotion + pullPx;
    return pullPx;
  }, []);

  const getLevitateMotion = (i) => {
    if (!levitate) return { x: 0, y: 0 };
    return levitateMotionByIndex[i] || { x: 0, y: 0 };
  };
  const getLevitateTransition = (i) => {
    if (!levitate) return {};
    if (levitateChaotic && levitateParams[i]) {
      const { dur, delay } = levitateParams[i];
      return {
        duration: dur,
        repeat: Infinity,
        repeatType: 'loop',
        ease: 'easeInOut',
        delay,
      };
    }
    return { duration: 6, repeat: Infinity, repeatType: 'loop', ease: 'easeInOut' };
  };

  const rowClass = 'flex items-center min-w-max';
  const spacerStyle = edgePadding > 0 ? { flexShrink: 0, width: edgePadding } : null;
  const itemStyle = (i) => ({
    width: baseW,
    minHeight: baseH,
    ...(overlapPx !== 0 && i < items.length - 1 ? { marginRight: overlapPx } : {}),
    ...(selectByCenter ? { scrollSnapAlign: 'center' } : {}),
  });
  const rowContent = (
    <>
      {spacerStyle ? <div style={spacerStyle} aria-hidden /> : null}
      {items.map((item, i) => {
        const isSelected = item.id === selectedId;
        const itemScale = getDistanceScale(i, isSelected);
        const pullPx = getCenterPullPx(i);
        const levitateMotion = getLevitateMotion(i);
        const domIndex = i + (spacerStyle ? 1 : 0);
        return (
          <motion.button
            key={item.id}
            initial={false}
            type="button"
            data-scroll-item
            onClick={() => handleItemClick(item, domIndex)}
            className="shrink-0 flex flex-col items-center cursor-pointer bg-transparent border-0 shadow-none"
            style={itemStyle(i)}
            animate={{
              scale: itemScale,
              opacity: isSelected ? 1 : 0.88,
              x: withCenterPull(levitateMotion.x, pullPx),
              y: levitateMotion.y,
            }}
            transition={{
              scale: { duration: 0.12, ease: 'easeOut' },
              opacity: { duration: 0.2 },
              x: getLevitateTransition(i),
              y: getLevitateTransition(i),
            }}
            whileTap={{ scale: isSelected ? scaleSel * 1.05 : itemScale * 0.98 }}
          >
            {renderItem ? renderItem(item, isSelected) : null}
          </motion.button>
        );
      })}
      {spacerStyle ? <div style={spacerStyle} aria-hidden /> : null}
    </>
  );

  const content = swayPx > 0 ? (
    <motion.div
      data-scroll-row
      className={rowClass}
      style={{ gap }}
      animate={{ x: [0, swayPx, 0, -swayPx, 0] }}
      transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
    >
      {rowContent}
    </motion.div>
  ) : (
    <div data-scroll-row className={rowClass} style={{ gap }}>
      {rowContent}
    </div>
  );

  const handleItemClick = useCallback((item, domIndex) => {
    if (selectByCenter && scrollRef.current) {
      const el = scrollRef.current;
      const row = el.querySelector('[data-scroll-row]');
      if (!row || !row.children[domIndex]) return;
      const itemEl = row.children[domIndex];
      const targetScroll = itemEl.offsetLeft - el.clientWidth / 2 + itemEl.offsetWidth / 2;
      el.scrollTo({ left: Math.max(0, targetScroll), behavior: 'smooth' });
    } else if (onSelect) {
      onSelect(item.id);
    }
  }, [selectByCenter, onSelect]);

  return (
    <div className={cn('relative', className)}>
      <div
        ref={scrollRef}
        className={cn(
          'overflow-x-scroll overflow-y-hidden scrollbar-hide',
          overflowVisible ? 'pt-6 pb-4' : 'py-3'
        )}
        style={{
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          WebkitOverflowScrolling: 'touch',
          overscrollBehaviorX: 'contain',
          touchAction: 'pan-x',
          ...(selectByCenter ? { scrollSnapType: 'x mandatory' } : {}),
        }}
      >
        {content}
      </div>
    </div>
  );
}
