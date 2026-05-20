let magicBallPrewarmPromise = null;

async function warmupWebGlContext() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const canvas = document.createElement('canvas');
  canvas.width = 8;
  canvas.height = 8;

  const attrs = {
    alpha: true,
    antialias: false,
    depth: true,
    stencil: false,
    preserveDrawingBuffer: false,
    powerPreference: 'high-performance',
  };

  const gl =
    canvas.getContext('webgl2', attrs)
    || canvas.getContext('webgl', attrs)
    || canvas.getContext('experimental-webgl', attrs);

  if (!gl) return;
  try {
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.finish?.();
  } catch (_) {}
}

export function prewarmMagicBall3D() {
  if (magicBallPrewarmPromise) return magicBallPrewarmPromise;

  magicBallPrewarmPromise = (async () => {
    // Preload heavy 3D chunk ahead of first navigation to /magic-ball.
    await import('../components/magic8ball/Magic8Ball').catch(() => {});
    await warmupWebGlContext();
  })();

  return magicBallPrewarmPromise;
}

