// RedCase Cron Worker — Cloudflare Cron Triggers (Task 1.7 step 5).
// Two triggers (UTC; 07:00 Africa/Lagos == 06:00 UTC, no DST in Nigeria):
//   */10 * * * *  keep-alive: GET  /v1/health (also warms scale-to-zero)
//   0 6 * * *     daily backfill: POST /v1/internal/sweep
// Token arrives as the INTERNAL_SWEEP_TOKEN worker secret (wrangler secret
// put) — never hardcoded here.

const HEALTH_CRON = "*/10 * * * *";
const SWEEP_CRON = "0 6 * * *";

export default {
  async scheduled(event, env, ctx) {
    if (event.cron === SWEEP_CRON) {
      ctx.waitUntil(runSweep(env));
    } else if (event.cron === HEALTH_CRON) {
      ctx.waitUntil(runHealth(env));
    }
    // Unknown cron expressions: fail silently rather than guess. A new
    // trigger must be added to wrangler.toml AND this dispatch together.
  },
};

async function runHealth(env) {
  const res = await fetch(`${env.API_BASE_URL}/v1/health`);
  if (!res.ok) {
    // Logged to the Workers runtime logs (wrangler tail / dashboard).
    console.error(`keep-alive failed: ${res.status}`);
  }
  return res;
}

async function runSweep(env) {
  const res = await fetch(`${env.API_BASE_URL}/v1/internal/sweep`, {
    method: "POST",
    headers: { "X-Internal-Token": env.INTERNAL_SWEEP_TOKEN },
  });
  if (!res.ok) {
    console.error(`sweep failed: ${res.status}`);
    return res;
  }
  const body = await res.json();
  // Counts only — ZDR: no document text ever crosses this log line.
  console.log(`sweep done: pending=${body.pending} embedded=${body.embedded}`);
  return res;
}
