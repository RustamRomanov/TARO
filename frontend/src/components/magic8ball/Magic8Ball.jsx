import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

import ErrorBoundary from '../ErrorBoundary';
import { Magic8BallLiteModal } from './Magic8BallShared';

const BASE_ROT_X = 0;
const BASE_ROT_Y = 0;
const DRAG_SENSITIVITY = 0.01;
const BASE_BALL_SCALE = 1.45;
const PREDICTION_BALL_SCALE = BASE_BALL_SCALE * 1.3;
const PRE_SPIN_DIP_SCALE = BASE_BALL_SCALE * 0.9;
const FRONT_FLAT_Z = 0.8;
const NORMAL_SCALE = new THREE.Vector2(0.14, 0.14);

function normalizeAngleRad(value) {
  return THREE.MathUtils.euclideanModulo(value + Math.PI, Math.PI * 2) - Math.PI;
}

function dampAngleRad(current, target, smoothing, delta) {
  const shortestDelta = normalizeAngleRad(target - current);
  return current + shortestDelta * (1 - Math.exp(-smoothing * delta));
}

function getMagicBallQualityProfile() {
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const reducedMotion =
    typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cores = Number(nav?.hardwareConcurrency || 4);
  const memory = Number(nav?.deviceMemory || 4);

  const lowTier = reducedMotion || cores <= 4 || memory <= 4;
  const mediumTier = !lowTier && (cores <= 8 || memory <= 8);

  return {
    reducedMotion,
    lowTier,
    mediumTier,
    initialLevel: lowTier ? 'low' : (mediumTier ? 'medium' : 'high'),
    warmTargetLevel: lowTier ? 'low' : (mediumTier ? 'medium' : 'high'),
    warmUpgradeDelayMs: lowTier ? 0 : 350,
    dynamicQualityEnabled: !reducedMotion,
  };
}

function buildMagicBallQuality(deviceProfile, level) {
  const normalizedLevel = level === 'low' || level === 'medium' || level === 'high'
    ? level
    : 'medium';
  const clampedLevel = deviceProfile?.lowTier
    ? 'low'
    : (deviceProfile?.mediumTier && normalizedLevel === 'high' ? 'medium' : normalizedLevel);

  if (clampedLevel === 'low') {
    return {
      sphereSegments: 56,
      ringSegments: 80,
      circleSegments: 40,
      normalMapSize: 192,
      scratchLines: 110,
      scratchPatches: 50,
      backLabelWidth: 1024,
      backLabelHeight: 512,
      answerPixelScale: 3,
      maxDpr: 1.15,
      antialias: false,
      idleMotion: false,
      powerPreference: 'default',
    };
  }

  if (clampedLevel === 'medium') {
    return {
      sphereSegments: 84,
      ringSegments: 124,
      circleSegments: 60,
      normalMapSize: 256,
      scratchLines: 190,
      scratchPatches: 78,
      backLabelWidth: 1792,
      backLabelHeight: 896,
      answerPixelScale: 4,
      maxDpr: 1.45,
      antialias: true,
      idleMotion: !(deviceProfile?.reducedMotion),
      powerPreference: 'high-performance',
    };
  }

  return {
    sphereSegments: 96,
    ringSegments: 128,
    circleSegments: 64,
    normalMapSize: 256,
    scratchLines: 230,
    scratchPatches: 90,
    backLabelWidth: 2048,
    backLabelHeight: 1024,
    answerPixelScale: 4,
    maxDpr: 1.5,
    antialias: true,
    idleMotion: !(deviceProfile?.reducedMotion),
    powerPreference: 'high-performance',
  };
}

function setTextureColorSpace(texture) {
  if ('colorSpace' in texture) {
    texture.colorSpace = THREE.SRGBColorSpace;
  } else if ('encoding' in texture) {
    texture.encoding = THREE.sRGBEncoding;
  }
}

function createSurfaceNormalTexture(quality) {
  const canvas = document.createElement('canvas');
  const size = quality?.normalMapSize || 256;
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(canvas.width, canvas.height);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = Math.floor(118 + Math.random() * 20);
    img.data[i] = n;
    img.data[i + 1] = n;
    img.data[i + 2] = 255;
    img.data[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  // Fine random scratch lines to mimic glossy plastic micro-abrasions.
  ctx.save();
  ctx.globalAlpha = 0.4;
  ctx.strokeStyle = 'rgb(140,140,255)';
  for (let i = 0; i < (quality?.scratchLines || 230); i += 1) {
    const x = Math.random() * canvas.width;
    const y = Math.random() * canvas.height;
    const len = 12 + Math.random() * 42;
    const ang = (Math.random() - 0.5) * 0.8;
    ctx.lineWidth = 0.6 + Math.random() * 0.8;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.cos(ang) * len, y + Math.sin(ang) * len);
    ctx.stroke();
  }
  // Worn plastic micro-patches: subtle cloudy abrasion.
  for (let i = 0; i < (quality?.scratchPatches || 90); i += 1) {
    const x = Math.random() * canvas.width;
    const y = Math.random() * canvas.height;
    const r = 4 + Math.random() * 13;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(150,150,255,0.24)');
    g.addColorStop(1, 'rgba(128,128,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(5, 3);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  return texture;
}

function createFlattenedSphereGeometry(segments = 96) {
  const geometry = new THREE.SphereGeometry(1, segments, segments);
  const pos = geometry.attributes.position;
  const limit = 1 - FRONT_FLAT_Z * FRONT_FLAT_Z;
  for (let i = 0; i < pos.count; i += 1) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    if (z > FRONT_FLAT_Z && x * x + y * y <= limit + 1e-5) {
      pos.setZ(i, FRONT_FLAT_Z);
    }
  }
  pos.needsUpdate = true;
  geometry.computeVertexNormals();
  return geometry;
}

function createBackLabelTexture(quality) {
  const canvas = document.createElement('canvas');
  canvas.width = quality?.backLabelWidth || 2048;
  canvas.height = quality?.backLabelHeight || 1024;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const cx = canvas.width * 0.75;
  const cy = canvas.height * 0.5;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const gradient = ctx.createLinearGradient(cx - 260, cy - 130, cx + 260, cy + 140);
  gradient.addColorStop(0, 'rgba(255, 255, 255, 0.96)');
  gradient.addColorStop(0.5, 'rgba(232, 242, 255, 0.96)');
  gradient.addColorStop(1, 'rgba(198, 222, 255, 0.95)');
  ctx.fillStyle = gradient;
  for (let i = 0; i < 60; i += 1) {
    const x = cx + (Math.random() - 0.5) * 720;
    const y = cy + (Math.random() - 0.5) * 260;
    const r = Math.random() * 1.1 + 0.3;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(206, 226, 255, 0.22)';
    ctx.fill();
  }
  ctx.fillStyle = gradient;
  // Reduce rear label text even more per UX request.
  ctx.font = "700 8px 'Bion', system-ui, sans-serif";
  ctx.fillText('МАГИЧЕСКИЙ ШАР ПРЕДСКАЗАНИЙ', cx, cy - 18);
  ctx.font = "700 10px 'Bion', system-ui, sans-serif";
  ctx.fillText('ASTROV', cx, cy + 8);
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  setTextureColorSpace(texture);
  return texture;
}

function splitIntoLines(ctx, text, maxWidth, maxLines = 3) {
  if (!text || !text.trim()) return [];

  const words = text.trim().split(/\s+/);
  const lines = [];
  let current = words[0] || '';

  for (let i = 1; i < words.length; i += 1) {
    const candidate = `${current} ${words[i]}`;
    if (ctx.measureText(candidate).width <= maxWidth) {
      current = candidate;
    } else {
      lines.push(current);
      current = words[i];
    }
  }

  if (current) lines.push(current);

  if (lines.length <= maxLines) return lines;

  const trimmed = lines.slice(0, maxLines);
  let last = trimmed[maxLines - 1];

  while (ctx.measureText(`${last}…`).width > maxWidth && last.length > 1) {
    last = last.slice(0, -1);
  }

  trimmed[maxLines - 1] = `${last}…`;
  return trimmed;
}

function fitAnswerText(ctx, text, maxWidth) {
  const fontFamily = "'Bion', system-ui, -apple-system, sans-serif";
  for (let size = 92; size >= 46; size -= 4) {
    ctx.font = `700 ${size}px ${fontFamily}`;
    const lines = splitIntoLines(ctx, text, maxWidth, 3);
    const widest = lines.reduce(
      (max, line) => Math.max(max, ctx.measureText(line).width),
      0
    );

    if (lines.length <= 3 && widest <= maxWidth) {
      return { size, lines };
    }
  }

  ctx.font = `700 46px ${fontFamily}`;
  return {
    size: 46,
    lines: splitIntoLines(ctx, text, maxWidth, 3),
  };
}

/** Пиксельный экран: рисуем в малом разрешении, затем масштабируем без сглаживания. */
function createAnswerTexture(text, quality) {
  const pixelScale = quality?.answerPixelScale || 4;
  const w = 192;
  const h = 192;
  const canvas = document.createElement('canvas');
  canvas.width = w * pixelScale;
  canvas.height = h * pixelScale;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.scale(pixelScale, pixelScale);
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2;
  const cy = h / 2;
  const radius = 86;
  const isDefaultLabel = text == null;
  const hasAnswerText = typeof text === 'string' && text.trim().length > 0;

  const baseGradient = ctx.createRadialGradient(cx - 14, cy - 16, radius * 0.2, cx, cy, radius);
  baseGradient.addColorStop(0, '#66bcff');
  baseGradient.addColorStop(0.45, '#2d73dc');
  baseGradient.addColorStop(1, '#12377f');

  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fillStyle = baseGradient;
  ctx.fill();

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, radius - 1, 0, Math.PI * 2);
  ctx.clip();
  // RGB phosphor-like pixel columns to imitate retro monitor structure.
  const px = 4;
  for (let y = 0; y < h; y += px) {
    for (let x = 0; x < w; x += px) {
      const mx = x + px * 0.5;
      const my = y + px * 0.5;
      const dx = mx - cx;
      const dy = my - cy;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d > radius - 1) continue;
      const depth = 1 - d / radius;
      const lum = 0.5 + depth * 0.55 + Math.random() * 0.18;
      const alpha = 0.22 + depth * 0.22;
      const rw = Math.max(1, Math.floor(px / 3));
      ctx.fillStyle = `rgba(${Math.floor(120 * lum)}, ${Math.floor(60 * lum)}, ${Math.floor(70 * lum)}, ${alpha})`;
      ctx.fillRect(x, y, rw, px - 1);
      ctx.fillStyle = `rgba(${Math.floor(70 * lum)}, ${Math.floor(155 * lum)}, ${Math.floor(95 * lum)}, ${alpha})`;
      ctx.fillRect(x + rw, y, rw, px - 1);
      ctx.fillStyle = `rgba(${Math.floor(75 * lum)}, ${Math.floor(110 * lum)}, ${Math.floor(230 * lum)}, ${alpha})`;
      ctx.fillRect(x + rw * 2, y, rw + 1, px - 1);
    }
  }
  ctx.restore();

  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(215,232,255,0.26)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  if (hasAnswerText) {

    const fontFamily = "'Silkscreen', 'Courier New', monospace";
    let smallSize = 18;
    let lines = [];
    while (smallSize >= 10) {
      ctx.font = `bold ${smallSize}px ${fontFamily}`;
      lines = splitIntoLines(ctx, text, 142, 3);
      const widest = lines.reduce((max, line) => Math.max(max, ctx.measureText(line).width), 0);
      if (widest <= 142 && lines.length <= 3) break;
      smallSize -= 1;
      if (smallSize <= 12) break;
    }
    ctx.font = `bold ${smallSize}px ${fontFamily}`;
    const lineHeight = smallSize + 2;
    const startY = cy - ((lines.length - 1) * lineHeight) / 2;

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
    ctx.strokeStyle = 'rgba(0, 10, 40, 0.75)';
    ctx.lineWidth = 1;

    lines.forEach((line, index) => {
      const y = startY + index * lineHeight;
      ctx.strokeText(line, cx, y);
      ctx.fillText(line, cx, y);
    });
  } else if (isDefaultLabel) {
    ctx.font = "bold 26px 'Silkscreen', monospace";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.72)';
    ctx.fillText('Узнай', cx, cy);
  }

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.NearestFilter;
  texture.magFilter = THREE.NearestFilter;
  texture.anisotropy = 1;
  setTextureColorSpace(texture);
  return texture;
}

function AnswerPlate({ text, quality }) {
  const texture = useMemo(() => createAnswerTexture(text, quality), [text, quality]);

  useEffect(() => {
    return () => {
      texture.dispose();
    };
  }, [texture]);

  return (
    <mesh position={[0, -0.01, 0.742]}>
      <circleGeometry args={[0.41, quality?.circleSegments || 64]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={1}
        alphaTest={0.03}
        depthWrite={false}
        depthTest={false}
        toneMapped={false}
      />
    </mesh>
  );
}

function BackLabel({ quality }) {
  const texture = useMemo(() => createBackLabelTexture(quality), [quality]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <mesh scale={1.002}>
      <sphereGeometry args={[1, quality?.sphereSegments || 96, quality?.sphereSegments || 96]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={0.98}
        depthWrite={false}
        alphaTest={0.05}
        toneMapped={false}
      />
    </mesh>
  );
}

function BallModel({ answerText, isAnimating, hasResult, quality, onActivityChange }) {
  const { invalidate } = useThree();
  const groupRef = useRef(null);
  const pointerTargetRef = useRef(null);
  const activityRef = useRef(false);

  const dragRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
    lastX: 0,
    lastY: 0,
    baseX: BASE_ROT_X,
    baseY: BASE_ROT_Y,
    startedAt: 0,
  });

  const targetRef = useRef({
    x: BASE_ROT_X,
    y: BASE_ROT_Y,
    scale: BASE_BALL_SCALE,
  });

  const currentRef = useRef({
    x: BASE_ROT_X,
    y: BASE_ROT_Y,
    scale: BASE_BALL_SCALE,
  });
  const inertiaRef = useRef({
    vx: 0,
    vy: 0,
  });
  const autoSpinRef = useRef({
    active: false,
    startAt: 0,
    durationMs: 3000,
    baseX: 0,
    baseY: 0,
    spinX: 0,
    spinY: 0,
    finalY: 0,
    direction: 1,
    wobbleX: 0,
  });

  const normalTexture = useMemo(() => createSurfaceNormalTexture(quality), [quality]);
  const shellGeometry = useMemo(
    () => createFlattenedSphereGeometry(quality?.sphereSegments || 96),
    [quality]
  );

  useEffect(() => {
    return () => {
      normalTexture.dispose();
      shellGeometry.dispose();
    };
  }, [normalTexture, shellGeometry]);

  useEffect(() => {
    if (isAnimating) {
      const direction = Math.random() < 0.5 ? -1 : 1;
      const baseX = targetRef.current.x;
      const baseY = targetRef.current.y;
      const shortestToFront = THREE.MathUtils.euclideanModulo(
        BASE_ROT_Y - baseY + Math.PI,
        Math.PI * 2
      ) - Math.PI;
      autoSpinRef.current.active = true;
      autoSpinRef.current.direction = direction;
      autoSpinRef.current.startAt = performance.now();
      autoSpinRef.current.baseX = baseX;
      autoSpinRef.current.baseY = baseY;
      autoSpinRef.current.spinX = BASE_ROT_X - baseX;
      // One full random-direction turn and smooth finish to the front.
      autoSpinRef.current.spinY = shortestToFront + direction * Math.PI * 2;
      autoSpinRef.current.wobbleX = (Math.random() * 2 - 1) * (Math.PI * 0.8);
      autoSpinRef.current.finalY = 0;
      targetRef.current.scale = BASE_BALL_SCALE;
      inertiaRef.current.vx = 0;
      inertiaRef.current.vy = 0;
    } else if (hasResult) {
      targetRef.current.scale = PREDICTION_BALL_SCALE;
    } else {
      targetRef.current.scale = BASE_BALL_SCALE;
    }
    invalidate();
  }, [hasResult, isAnimating]);

  const handlePointerDown = useCallback(
    (event) => {
      if (isAnimating) return;

      event.stopPropagation();
      event.target?.setPointerCapture?.(event.pointerId);
      pointerTargetRef.current = event.target;

      dragRef.current.active = true;
      inertiaRef.current.vx = 0;
      inertiaRef.current.vy = 0;
      dragRef.current.startX = event.clientX;
      dragRef.current.startY = event.clientY;
      dragRef.current.lastX = event.clientX;
      dragRef.current.lastY = event.clientY;
      dragRef.current.baseX = targetRef.current.x;
      dragRef.current.baseY = targetRef.current.y;
      dragRef.current.startedAt = performance.now();
      invalidate();
    },
    [invalidate, isAnimating]
  );

  const handlePointerMove = useCallback(
    (event) => {
      if (!dragRef.current.active || isAnimating) return;

      event.stopPropagation();

      const dx = event.clientX - dragRef.current.lastX;
      const dy = event.clientY - dragRef.current.lastY;
      targetRef.current.y += dx * DRAG_SENSITIVITY;
      targetRef.current.x += dy * DRAG_SENSITIVITY;
      dragRef.current.lastX = event.clientX;
      dragRef.current.lastY = event.clientY;
      invalidate();
    },
    [invalidate, isAnimating]
  );

  const handlePointerUp = useCallback(
    (event) => {
      if (!dragRef.current.active) return;

      event.stopPropagation();
      pointerTargetRef.current?.releasePointerCapture?.(event.pointerId);

      const dx = event.clientX - dragRef.current.startX;
      const dy = event.clientY - dragRef.current.startY;
      const duration = performance.now() - dragRef.current.startedAt;
      const vScreenX = dx / Math.max(duration, 1);
      const vScreenY = dy / Math.max(duration, 1);

      dragRef.current.active = false;
      pointerTargetRef.current = null;

      const spinFactor = 3.2;
      const minSpin = 0.8;
      const sx = Math.abs(vScreenX) > 0.02 ? vScreenX : (dx === 0 ? 0 : Math.sign(dx) * 0.22);
      const sy = Math.abs(vScreenY) > 0.02 ? vScreenY : (dy === 0 ? 0 : Math.sign(dy) * 0.22);
      inertiaRef.current.vx = THREE.MathUtils.clamp(sy * spinFactor, -5, 5);
      inertiaRef.current.vy = THREE.MathUtils.clamp(sx * spinFactor, -5, 5);
      if (Math.abs(inertiaRef.current.vx) < minSpin) inertiaRef.current.vx = Math.sign(inertiaRef.current.vx || sy || 1) * minSpin;
      if (Math.abs(inertiaRef.current.vy) < minSpin) inertiaRef.current.vy = Math.sign(inertiaRef.current.vy || sx || 1) * minSpin;
      invalidate();

    },
    [invalidate, isAnimating]
  );

  useFrame((state, delta) => {
    const idleX =
      quality?.idleMotion && !dragRef.current.active && !isAnimating && !hasResult
        ? Math.sin(state.clock.elapsedTime * 0.6) * 0.025
        : 0;

    const idleY =
      quality?.idleMotion && !dragRef.current.active && !isAnimating && !hasResult
        ? Math.cos(state.clock.elapsedTime * 0.55) * 0.03
        : 0;

    if (autoSpinRef.current.active) {
      const elapsed = performance.now() - autoSpinRef.current.startAt;
      const t = THREE.MathUtils.clamp(elapsed / autoSpinRef.current.durationMs, 0, 1);
      const eased = t * t * (3 - 2 * t);
      const wobble = Math.sin(Math.PI * t) * (1 - eased);
      targetRef.current.x = autoSpinRef.current.baseX + autoSpinRef.current.spinX * eased + autoSpinRef.current.wobbleX * wobble;
      targetRef.current.y = autoSpinRef.current.baseY + autoSpinRef.current.spinY * eased;
      const dipPhaseEnd = 0.34;
      if (t < dipPhaseEnd) {
        const dipT = THREE.MathUtils.clamp(t / dipPhaseEnd, 0, 1);
        const dipEase = dipT * dipT * (3 - 2 * dipT);
        targetRef.current.scale = THREE.MathUtils.lerp(BASE_BALL_SCALE, PRE_SPIN_DIP_SCALE, dipEase);
      } else {
        const growT = THREE.MathUtils.clamp((t - dipPhaseEnd) / (1 - dipPhaseEnd), 0, 1);
        const growEase = growT * growT * (3 - 2 * growT);
        targetRef.current.scale = THREE.MathUtils.lerp(PRE_SPIN_DIP_SCALE, PREDICTION_BALL_SCALE, growEase);
      }
      if (t >= 1) {
        autoSpinRef.current.active = false;
        targetRef.current.x = BASE_ROT_X;
        targetRef.current.y = normalizeAngleRad(targetRef.current.y);
        targetRef.current.scale = PREDICTION_BALL_SCALE;
        inertiaRef.current.vx = 0;
        inertiaRef.current.vy = 0;
      }
    } else if (!dragRef.current.active && !isAnimating) {
      targetRef.current.x += inertiaRef.current.vx * delta * 3.7;
      targetRef.current.y += inertiaRef.current.vy * delta * 3.7;
      inertiaRef.current.vx = THREE.MathUtils.damp(inertiaRef.current.vx, 0, 1.45, delta);
      inertiaRef.current.vy = THREE.MathUtils.damp(inertiaRef.current.vy, 0, 1.45, delta);
      const restoreSpeed = hasResult ? 0.85 : 1.2;
      targetRef.current.x = THREE.MathUtils.damp(targetRef.current.x, BASE_ROT_X, restoreSpeed, delta);
      targetRef.current.y = dampAngleRad(targetRef.current.y, BASE_ROT_Y, restoreSpeed, delta);
    } else if (isAnimating) {
      inertiaRef.current.vx = THREE.MathUtils.damp(inertiaRef.current.vx, 0, 16, delta);
      inertiaRef.current.vy = THREE.MathUtils.damp(inertiaRef.current.vy, 0, 16, delta);
    }

    currentRef.current.x = THREE.MathUtils.damp(
      currentRef.current.x,
      targetRef.current.x + idleX,
      dragRef.current.active ? 18 : 8,
      delta
    );

    currentRef.current.y = dampAngleRad(
      currentRef.current.y,
      targetRef.current.y + idleY,
      dragRef.current.active ? 18 : 8,
      delta
    );

    currentRef.current.scale = THREE.MathUtils.damp(
      currentRef.current.scale,
      targetRef.current.scale,
      autoSpinRef.current.active ? 8 : 4,
      delta
    );

    if (groupRef.current) {
      groupRef.current.rotation.x = currentRef.current.x;
      groupRef.current.rotation.y = currentRef.current.y;
      groupRef.current.scale.setScalar(currentRef.current.scale);
    }

    const targetX = targetRef.current.x + idleX;
    const targetY = targetRef.current.y + idleY;
    const hasInertia =
      Math.abs(inertiaRef.current.vx) > 0.015
      || Math.abs(inertiaRef.current.vy) > 0.015;
    const unsettled =
      Math.abs(currentRef.current.x - targetX) > 0.0015
      || Math.abs(currentRef.current.y - targetY) > 0.0015
      || Math.abs(currentRef.current.scale - targetRef.current.scale) > 0.0015;
    const activeNow =
      dragRef.current.active
      || autoSpinRef.current.active
      || hasInertia
      || unsettled
      || Boolean(isAnimating);

    if (activityRef.current !== activeNow) {
      activityRef.current = activeNow;
      onActivityChange?.(activeNow);
    }
    if (activeNow) invalidate();
  });

  useEffect(
    () => () => {
      if (activityRef.current) onActivityChange?.(false);
    },
    [onActivityChange]
  );

  return (
    <group
      ref={groupRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <mesh castShadow receiveShadow geometry={shellGeometry}>
        <meshPhysicalMaterial
          color="#4a2d62"
          metalness={0.26}
          roughness={0.03}
          clearcoat={1}
          clearcoatRoughness={0.006}
          envMapIntensity={3.45}
          reflectivity={1}
          specularIntensity={1}
          specularColor="#f5f0ff"
          normalMap={normalTexture}
          normalScale={NORMAL_SCALE}
        />
      </mesh>

      <mesh scale={0.992} geometry={shellGeometry}>
        <meshBasicMaterial
          color="#181c24"
          transparent
          opacity={0.12}
          side={THREE.BackSide}
        />
      </mesh>

      <mesh position={[0, 0, 0.786]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.455, 0.455, 0.045, quality?.circleSegments || 64]} />
        <meshStandardMaterial
          color="#090c11"
          metalness={0.06}
          roughness={0.62}
        />
      </mesh>

      <mesh position={[0, 0, 0.736]}>
        <circleGeometry args={[0.422, quality?.circleSegments || 64]} />
        <meshStandardMaterial
          color="#05070b"
          metalness={0.03}
          roughness={0.76}
        />
      </mesh>

      <mesh position={[0, 0, 0.742]}>
        <circleGeometry args={[0.43, quality?.circleSegments || 64]} />
        <meshBasicMaterial
          color="#9d6fe0"
          transparent
          opacity={0.52}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>

      <mesh position={[0, 0, 0.74]}>
        <circleGeometry args={[0.418, quality?.circleSegments || 64]} />
        <meshBasicMaterial
          color="#6b48b8"
          transparent
          opacity={0.46}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>

      <pointLight
        position={[0, 0, 1.08]}
        intensity={1.72}
        distance={2.2}
        color="#c4b5fd"
      />

      <AnswerPlate text={answerText} quality={quality} />
      <BackLabel quality={quality} />

      <mesh position={[0, 0, 0.812]}>
        <circleGeometry args={[0.421, quality?.circleSegments || 64]} />
        <meshBasicMaterial
          color="#5a3d78"
          transparent
          opacity={0.08}
          toneMapped={false}
        />
      </mesh>

      <mesh position={[0, 0, 0.816]}>
        <torusGeometry args={[0.432, 0.022, 18, quality?.ringSegments || 128]} />
        <meshStandardMaterial
          color="#0a0d12"
          metalness={0.2}
          roughness={0.22}
        />
      </mesh>

      <mesh position={[0, 0, 0.818]}>
        <torusGeometry args={[0.422, 0.0048, 14, quality?.ringSegments || 128]} />
        <meshBasicMaterial color="#07090c" toneMapped={false} />
      </mesh>
    </group>
  );
}

function SceneCameraRig({ isAnimating, hasResult, onActivityChange }) {
  const { camera, invalidate } = useThree();
  const activityRef = useRef(false);
  const lastFovRef = useRef(camera.fov);
  useFrame((_, delta) => {
    const expandedView = isAnimating || hasResult;
    const targetZ = expandedView ? 6.22 : 5.8;
    const targetFov = expandedView ? 38 : 34;
    camera.position.z = THREE.MathUtils.damp(camera.position.z, targetZ, 5, delta);
    const nextFov = THREE.MathUtils.damp(camera.fov, targetFov, 5, delta);
    camera.fov = nextFov;
    if (Math.abs(nextFov - lastFovRef.current) > 0.01) {
      camera.updateProjectionMatrix();
      lastFovRef.current = nextFov;
    }

    const cameraActive =
      Math.abs(camera.position.z - targetZ) > 0.003
      || Math.abs(nextFov - targetFov) > 0.01;
    if (activityRef.current !== cameraActive) {
      activityRef.current = cameraActive;
      onActivityChange?.(cameraActive);
    }
    if (cameraActive) invalidate();
  });
  useEffect(
    () => () => {
      if (activityRef.current) onActivityChange?.(false);
    },
    [onActivityChange]
  );
  return null;
}

function PerformanceGovernor({ enabled, level, onLevelChange, allowUpgrade, minLevel = 'low' }) {
  const statsRef = useRef({
    emaFps: 60,
    lowDurationMs: 0,
    highDurationMs: 0,
    cooldownUntil: 0,
  });

  useFrame((_, delta) => {
    if (!enabled) return;

    const now = performance.now();
    if (now < statsRef.current.cooldownUntil) return;

    const fps = 1 / Math.max(delta, 0.0001);
    statsRef.current.emaFps = statsRef.current.emaFps * 0.92 + fps * 0.08;
    const ema = statsRef.current.emaFps;

    const canDowngrade =
      (minLevel === 'low' && level !== 'low')
      || (minLevel === 'medium' && level === 'high');

    if (canDowngrade && ema < 34) {
      statsRef.current.lowDurationMs += delta * 1000;
    } else {
      statsRef.current.lowDurationMs = 0;
    }

    if (allowUpgrade && level !== 'high' && ema > 57) {
      statsRef.current.highDurationMs += delta * 1000;
    } else {
      statsRef.current.highDurationMs = 0;
    }

    if (statsRef.current.lowDurationMs >= 2400) {
      const next = level === 'high' ? 'medium' : minLevel;
      onLevelChange?.(next);
      statsRef.current.lowDurationMs = 0;
      statsRef.current.highDurationMs = 0;
      statsRef.current.cooldownUntil = now + 4200;
      return;
    }

    if (statsRef.current.highDurationMs >= 3600) {
      const next = level === 'low' ? 'medium' : 'high';
      onLevelChange?.(next);
      statsRef.current.lowDurationMs = 0;
      statsRef.current.highDurationMs = 0;
      statsRef.current.cooldownUntil = now + 5200;
    }
  });

  return null;
}

function Magic8BallScene({ answerText, isAnimating, hasResult }) {
  const deviceProfile = useMemo(() => getMagicBallQualityProfile(), []);
  const [qualityLevel, setQualityLevel] = useState(deviceProfile.initialLevel);
  const quality = useMemo(
    () => buildMagicBallQuality(deviceProfile, qualityLevel),
    [deviceProfile, qualityLevel]
  );
  const [ballActive, setBallActive] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const shouldAnimateScene = isAnimating || ballActive || cameraActive;
  const handleQualityChange = useCallback(
    (nextLevel) => {
      setQualityLevel((current) => (current === nextLevel ? current : nextLevel));
    },
    []
  );

  useEffect(() => {
    if (!deviceProfile.dynamicQualityEnabled) return undefined;
    if (deviceProfile.warmUpgradeDelayMs <= 0) return undefined;
    if (deviceProfile.warmTargetLevel === deviceProfile.initialLevel) return undefined;

    const t = window.setTimeout(() => {
      setQualityLevel((current) => (
        current === deviceProfile.initialLevel
          ? deviceProfile.warmTargetLevel
          : current
      ));
    }, deviceProfile.warmUpgradeDelayMs);

    return () => window.clearTimeout(t);
  }, [deviceProfile]);

  return (
    <Canvas
      shadows
      frameloop={shouldAnimateScene ? 'always' : 'demand'}
      dpr={[1, quality.maxDpr]}
      gl={{ antialias: quality.antialias, alpha: true, powerPreference: quality.powerPreference }}
      camera={{ position: [0, 0, 5.8], fov: 34 }}
      style={{ width: '100%', height: '100%', touchAction: 'none' }}
    >
      <PerformanceGovernor
        enabled={Boolean(deviceProfile.dynamicQualityEnabled)}
        level={qualityLevel}
        onLevelChange={handleQualityChange}
        allowUpgrade={!isAnimating}
        minLevel="medium"
      />
      <SceneCameraRig isAnimating={isAnimating} hasResult={hasResult} onActivityChange={setCameraActive} />
      <ambientLight intensity={0.14} />
      <directionalLight
        position={[3.4, 2.1, 3.8]}
        intensity={3.0}
        color="#f5f0ff"
      />
      <directionalLight
        position={[-2.2, 1.3, 2.4]}
        intensity={1.1}
        color="#e8ddff"
      />
      <pointLight
        position={[0, -2.0, 2.8]}
        intensity={2.0}
        distance={10}
        color="#c4b5fd"
      />

      <BallModel
        answerText={answerText}
        isAnimating={isAnimating}
        hasResult={hasResult}
        quality={quality}
        onActivityChange={setBallActive}
      />

      
    </Canvas>
  );
}

export default function Magic8Ball({
  open,
  onClose,
  variant = 'modal',
  answer,
  isAnimating,
  hasResult,
  triggerPrediction,
  resetBall,
  sceneKey = 0,
  secondaryAction = null,
}) {
  const isPage = variant === 'page';

  useEffect(() => {
    if (!open || isPage) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose, isPage]);

  const handlePrimaryAction = () => {
    if (isAnimating) return;
    triggerPrediction(3000);
  };

  if (!open) return null;
  const expandedView = isAnimating || hasResult;

  const hintAndButton = (
    <div
      style={
        isPage
          ? {
              position: 'fixed',
              left: 0,
              right: 0,
              bottom: secondaryAction
                ? 'calc(1.25rem + env(safe-area-inset-bottom, 0px))'
                : 'calc(5.85rem + env(safe-area-inset-bottom, 0px))',
              zIndex: 20,
              padding: '0 12px',
              display: 'flex',
              justifyContent: 'center',
              pointerEvents: 'auto',
            }
          : {
              padding: '0 12px 14px',
              marginTop: 0,
              transform: 'translateY(-20%)',
              display: 'flex',
              justifyContent: 'center',
              position: 'relative',
              zIndex: 2,
            }
      }
    >
      <div style={{ maxWidth: 680, textAlign: 'center', color: '#e9e0ff' }}>
        <div style={{ fontSize: 13, fontWeight: 600, fontFamily: "'Bion', sans-serif" }}>
          Задайте вопрос в форме,
        </div>
        <div style={{ marginTop: 2, fontSize: 12, opacity: 0.85, fontFamily: "'Bion', sans-serif" }}>
          предполагающей ответ &quot;Да&quot; или &quot;Нет&quot;
        </div>
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
              ? '1px solid rgba(167,139,250,0.45)'
              : '1px solid rgba(167,139,250,0.35)',
            background: hasResult
              ? 'linear-gradient(180deg, rgba(109,40,217,0.5), rgba(76,29,149,0.55))'
              : 'linear-gradient(180deg, rgba(88,28,135,0.42), rgba(59,18,97,0.48))',
            boxShadow: hasResult
              ? '0 8px 20px rgba(76, 29, 149, 0.4), inset 0 1px 0 rgba(255,255,255,0.14)'
              : '0 8px 20px rgba(24, 10, 40, 0.45), inset 0 1px 0 rgba(255,255,255,0.12)',
            color: '#f4f0ff',
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
                ? '1px solid rgba(167,139,250,0.45)'
                : '1px solid rgba(167,139,250,0.35)',
              background: hasResult
                ? 'linear-gradient(180deg, rgba(109,40,217,0.5), rgba(76,29,149,0.55))'
                : 'linear-gradient(180deg, rgba(88,28,135,0.42), rgba(59,18,97,0.48))',
              boxShadow: hasResult
                ? '0 8px 20px rgba(76, 29, 149, 0.4), inset 0 1px 0 rgba(255,255,255,0.14)'
                : '0 8px 20px rgba(24, 10, 40, 0.45), inset 0 1px 0 rgba(255,255,255,0.12)',
              color: '#f4f0ff',
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
  );

  const ballBlock = (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 0 0',
        overflow: 'visible',
        position: 'relative',
        zIndex: hasResult ? 12 : 1,
      }}
    >
      <div
        style={{
          width: 'min(104vw, 1220px)',
          aspectRatio: '1 / 1',
          maxHeight: expandedView ? (isPage ? '72vh' : '98vh') : isPage ? '58vh' : '90vh',
          cursor: isAnimating ? 'default' : 'grab',
          overflow: 'visible',
          position: 'relative',
          margin: '0 auto',
          transform: isPage ? 'translateY(0%)' : 'translateY(4%)',
          zIndex: expandedView ? 14 : 3,
        }}
      >
        <Magic8BallScene
          key={sceneKey}
          answerText={answer ?? 'Узнай'}
          isAnimating={isAnimating}
          hasResult={hasResult}
        />
      </div>
    </div>
  );

  const closeButton = !isPage ? (
    <button
      type="button"
      onClick={onClose}
      style={{
        position: 'absolute',
        top: 14,
        right: 14,
        zIndex: 40,
        width: 44,
        height: 44,
        borderRadius: 999,
        border: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(255,255,255,0.05)',
        color: '#e8ecff',
        fontSize: 24,
        cursor: 'pointer',
        backdropFilter: 'blur(8px)',
      }}
      aria-label="Закрыть"
    >
      ×
    </button>
  ) : null;

  const modalCardInner = (
    <>
      {closeButton}
      {ballBlock}
      {hintAndButton}
    </>
  );

  const pageCardStyle = {
    position: 'relative',
    width: '100%',
    maxWidth: 'min(980px, 100%)',
    margin: '0 auto',
    minHeight: 0,
    flex: 1,
    borderRadius: '28px',
    overflow: 'visible',
    background: 'transparent',
    border: 'none',
    boxShadow: 'none',
    backdropFilter: 'none',
    WebkitBackdropFilter: 'none',
    display: 'flex',
    flexDirection: 'column',
  };

  const modalCardStyle = {
    position: 'relative',
    width: 'min(980px, 100%)',
    minHeight: 'min(636px, 100vh - 6px)',
    borderRadius: '28px',
    overflow: 'visible',
    background:
      'radial-gradient(110% 90% at 50% 46%, rgba(34,48,82,0.34) 0%, rgba(16,22,38,0.58) 46%, rgba(8,11,20,0.76) 100%)',
    border: '1px solid rgba(145, 168, 255, 0.12)',
    boxShadow:
      '0 24px 70px rgba(0,0,0,0.42), inset 0 1px 0 rgba(255,255,255,0.04)',
    backdropFilter: 'blur(16px) saturate(115%)',
    WebkitBackdropFilter: 'blur(16px) saturate(115%)',
    display: 'flex',
    flexDirection: 'column',
  };

  const pageBody = (
    <div className="flex flex-1 flex-col min-h-0 w-full">
      <div style={pageCardStyle}>{ballBlock}</div>
      {hintAndButton}
    </div>
  );

  const modalCard = (
    <motion.div
      initial={{ scale: 0.96, opacity: 0, y: 18 }}
      animate={{ scale: 1, opacity: 1, y: 0 }}
      exit={{ scale: 0.98, opacity: 0, y: 10 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      style={modalCardStyle}
    >
      {modalCardInner}
    </motion.div>
  );

  const modalContent = (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
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
            padding: '6px 10px 0',
          }}
        >
          {modalCard}
        </motion.div>
      )}
    </AnimatePresence>
  );

  return (
    <ErrorBoundary
      fallback={
        <Magic8BallLiteModal
          onClose={onClose}
          answer={answer}
          isAnimating={isAnimating}
          hasResult={hasResult}
          triggerPrediction={triggerPrediction}
          resetBall={resetBall}
        />
      }
    >
      {isPage ? pageBody : modalContent}
    </ErrorBoundary>
  );
}
