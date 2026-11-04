// Ledger traffic, for play and for the verifier's replay.
// Env: TARGET (base URL), VUS, DURATION, ATTACK_RATE (share of iterations where a customer
// fires two payments at once for most of their balance, as a double-click or two open tabs
// would; default 0), HOT_ACCOUNTS (comma list of accounts that keep paying each other, both
// ways, like marketplace sellers settling up; default none), P99_MS and ERROR_RATE.
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const target = __ENV.TARGET || "http://api:8000";
const vus = Number(__ENV.VUS || 20);
const duration = __ENV.DURATION || "3m";
const attackRate = Number(__ENV.ATTACK_RATE || 0);
const hot = (__ENV.HOT_ACCOUNTS || "").split(",").filter(Boolean).map(Number);
const p99 = Number(__ENV.P99_MS || 500);
const errorRate = Number(__ENV.ERROR_RATE || 0.01);

export const options = {
  vus,
  duration,
  thresholds: {
    http_req_duration: [`p(99)<${p99}`],
    http_req_failed: [`rate<${errorRate}`],
  },
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
};

// A 409 is an answer, not a failure: the customer didn't have the money.
const refusalOk = http.expectedStatuses(201, 409);
const json = { "Content-Type": "application/json" };
const overdrawn = new Rate("double_spends");

const customer = () => 1 + Math.floor(Math.random() * 1000);
const merchant = () => 9001 + Math.floor(Math.random() * 20);
const cents = (min, max) => min + Math.floor(Math.random() * (max - min));

function post(path, body, name) {
  return http.post(`${target}${path}`, JSON.stringify(body), {
    headers: json,
    tags: { name },
    responseCallback: refusalOk,
  });
}

function attack() {
  // Two payments at once, each for 70% of the balance: at most one can be covered.
  const id = customer();
  const res = http.get(`${target}/accounts/${id}`, { tags: { name: "account" } });
  if (res.status !== 200) return;
  const balance = res.json("balance_cents");
  if (balance < 2000) {
    post("/transfers", { from_account: 0, to_account: id, amount_cents: 50000 }, "top_up");
    return;
  }
  const amount = Math.floor(balance * 0.7);
  const body = JSON.stringify({ account_id: id, merchant_id: merchant(), amount_cents: amount });
  const params = { headers: json, tags: { name: "payment" }, responseCallback: refusalOk };
  const both = http.batch([
    ["POST", `${target}/payments`, body, params],
    ["POST", `${target}/payments`, body, params],
  ]);
  overdrawn.add(both.every((r) => r.status === 201));
}

export default function () {
  if (attackRate > 0 && Math.random() < attackRate) {
    attack();
  } else if (hot.length > 1 && Math.random() < 0.5) {
    // Hot accounts pay each other back and forth.
    const a = hot[Math.floor(Math.random() * hot.length)];
    let b = hot[Math.floor(Math.random() * hot.length)];
    if (b === a) b = hot[(hot.indexOf(a) + 1) % hot.length];
    const res = post("/transfers", { from_account: a, to_account: b, amount_cents: cents(100, 2000) }, "hot");
    check(res, { "hot transfer": (r) => r.status === 201 || r.status === 409 });
  } else {
    const roll = Math.random();
    if (roll < 0.5) {
      const res = http.get(`${target}/accounts/${customer()}`, { tags: { name: "account" } });
      check(res, { "account 200": (r) => r.status === 200 });
    } else if (roll < 0.75) {
      const res = post(
        "/payments",
        { account_id: customer(), merchant_id: merchant(), amount_cents: cents(500, 5000) },
        "payment",
      );
      check(res, { payment: (r) => r.status === 201 || r.status === 409 });
    } else if (roll < 0.9) {
      let to = customer();
      const from = customer();
      if (to === from) to = (to % 1000) + 1;
      const res = post(
        "/transfers",
        { from_account: from, to_account: to, amount_cents: cents(100, 3000) },
        "transfer",
      );
      check(res, { transfer: (r) => r.status === 201 || r.status === 409 });
    } else {
      // Top-ups from the house keep wallets from running dry.
      post(
        "/transfers",
        { from_account: 0, to_account: customer(), amount_cents: cents(5000, 20000) },
        "top_up",
      );
    }
  }
  sleep(0.05);
}

export function handleSummary(data) {
  // One JSON line the verifier parses (k6's own summary goes to stdout as well).
  const metric = (name) => data.metrics[name] || {};
  const out = {
    p99_ms: metric("http_req_duration").values?.["p(99)"] ?? null,
    p95_ms: metric("http_req_duration").values?.["p(95)"] ?? null,
    error_rate: metric("http_req_failed").values?.rate ?? null,
    requests: metric("http_reqs").values?.count ?? 0,
    double_spends: metric("double_spends").values?.rate ?? null,
    thresholds_passed: Object.values(data.metrics).every(
      (m) => !m.thresholds || Object.values(m.thresholds).every((t) => t.ok),
    ),
  };
  return { stdout: JSON.stringify(out) + "\n" };
}
