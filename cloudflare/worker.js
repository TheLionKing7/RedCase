// RedCase Cron Worker — Cloudflare Cron Trigger (Task 1.7 step 5).
//
// Single trigger to stay within the account's free-plan cron limit (5 max);
// the daily/time-critical work is gated inside the handler on wall-clock UTC
// (Africa/Lagos is UTC+1 year-round, no DST, so 07:00 Lagos == 06:00 UTC):
//
//   */5 * * * *   every 5 min  -> GET  /v1/health        (keep-alive / warm)
//                 at 06:00 UTC -> POST /v1/internal/sweep (daily backfill)
//
// The sweep token arrives as the INTERNAL_SWEEP_TOKEN worker secret
// (`wrangler secret put`), never hardcoded here.

export default {
  async scheduled(event, env, ctx) {
    const now = new Date();
    const isSixUtc = now.getUTCHours() === 6 && now.getUTCMinutes() === 0;

    // Keep-alive on every tick (supersedes the old */10 keep-alive).
    ctx.waitUntil(runHealth(env));
    // Daily backfill, once per day at 06:00 UTC.
    if (isSixUtc) {
      ctx.waitUntil(runSweep(env));
    }
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
