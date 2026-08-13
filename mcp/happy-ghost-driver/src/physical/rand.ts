/**
 * Human-like random distribution utilities.
 *
 * All physical modules should use these instead of Math.random() directly.
 * A Gaussian (normal) distribution produces timing intervals whose statistical
 * shape matches real human behaviour far better than uniform random: most
 * values cluster around a central tendency, with occasional short bursts and
 * longer pauses that uniform random never generates.
 *
 * Box-Muller transform converts two uniform samples into one Gaussian.
 */

/**
 * Raw Gaussian sample via Box-Muller.  Mean = 0, stdDev = 1.
 * Caller must clamp if a bounded range is needed.
 */
function standardNormal(): number {
  const u1 = Math.random();
  const u2 = Math.random();
  // Guard against log(0).
  const safe = u1 > 0 ? u1 : Number.EPSILON;
  return Math.sqrt(-2 * Math.log(safe)) * Math.cos(2 * Math.PI * u2);
}

/**
 * Gaussian sample with given mean and standard deviation, clamped to [lo, hi]
 * and rounded to integer milliseconds.
 *
 * The mean defaults to the midpoint; stdDev to (range / 4) so ~95 % of
 * samples fall inside [lo, hi] before clamping.
 */
export function gaussianInt(lo: number, hi: number): number {
  const min = Math.min(lo, hi);
  const max = Math.max(lo, hi);
  if (min === max) return min;
  const mean = (min + max) / 2;
  const stdDev = (max - min) / 4;
  const raw = mean + standardNormal() * stdDev;
  return Math.max(min, Math.min(max, Math.round(raw)));
}

/**
 * Autoregressive (AR-1) jitter generator for keyboard typing.
 *
 * Maintains internal state so consecutive delays are *correlated*: a short
 * delay makes the next one more likely to be short too (burst typing), while
 * an occasional long delay creates a natural "thinking pause".  This matches
 * the autocorrelation observed in real keystroke timing (ρ ≈ 0.3).
 *
 * Usage:
 *   const gen = createArJitter(50, 200);
 *   const delay = gen.next();   // ms, clamped to [50, 200]
 */
export function createArJitter(lo: number, hi: number): { next: () => number } {
  const min = Math.min(lo, hi);
  const max = Math.max(lo, hi);
  const mean = (min + max) / 2;
  const stdDev = (max - min) / 4;
  // ρ = autocorrelation coefficient; 0.3 is a mild, human-like value.
  const rho = 0.3;
  // Initialise to the mean so the first sample isn't extreme.
  let prev: number = mean;

  return {
    next(): number {
      // AR(1): next = ρ * (prev - mean) + (1-ρ) * noise + mean
      const noise = standardNormal() * stdDev;
      const raw = mean + rho * (prev - mean) + (1 - rho) * noise;
      prev = raw;
      return Math.max(min, Math.min(max, Math.round(raw)));
    },
  };
}
