// ShopKart traffic shape, for play ("the sale") and for the verifier's replay.
// Env: TARGET (base URL), VUS, DURATION, HOT_KEYS (comma list of product ids that get most
// of the reads, like a sale landing page), SEARCH_TERMS (comma list of search queries, picked
// at random; repeat one to weight it), PRICE_UPDATE_RATE (share of iterations that also
// reprice a hot product, like a pricing job; default 0), ALSO_BOUGHT (1: product pages also load
// the "customers also bought" box, as the storefront does), RATE (iterations per second: an
// open model, where a slow system queues shoppers instead of slowing them down; default off,
// VUS shoppers in a loop), P99_MS and ERROR_RATE (thresholds).
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const target = __ENV.TARGET || "http://api:8000";
const hot = (__ENV.HOT_KEYS || "1042,1043,2210,77,9001").split(",").map(Number);
const searchTerms = (__ENV.SEARCH_TERMS || "Trail").split(",").map((s) => s.trim());
const priceUpdateRate = Number(__ENV.PRICE_UPDATE_RATE || 0);
const alsoBought = __ENV.ALSO_BOUGHT === "1";
const rate = Number(__ENV.RATE || 0);
const vus = Number(__ENV.VUS || 20);
const duration = __ENV.DURATION || "3m";
const p99 = Number(__ENV.P99_MS || 500);
const errorRate = Number(__ENV.ERROR_RATE || 0.01);

export const options = {
  ...(rate
    ? {
        scenarios: {
          shoppers: {
            executor: "constant-arrival-rate",
            rate,
            timeUnit: "1s",
            duration,
            preAllocatedVUs: vus,
            maxVUs: 500,
          },
        },
      }
    : { vus, duration }),
  thresholds: {
    http_req_duration: [`p(99)<${p99}`],
    http_req_failed: [`rate<${errorRate}`],
  },
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
};

const productLatency = new Trend("product_latency", true);
const productFailed = new Rate("product_failed");

function pick() {
  // 80% of reads go to the hot products, the rest spread over the catalogue.
  if (Math.random() < 0.8) return hot[Math.floor(Math.random() * hot.length)];
  return 1 + Math.floor(Math.random() * 18402);
}

export default function () {
  if (priceUpdateRate > 0 && Math.random() < priceUpdateRate) {
    const id = hot[Math.floor(Math.random() * hot.length)];
    http.put(
      `${target}/products/${id}/price`,
      JSON.stringify({ price_cents: 999 + Math.floor(Math.random() * 9000) }),
      { headers: { "Content-Type": "application/json" }, tags: { name: "price" } },
    );
  }
  const roll = Math.random();
  if (roll < 0.85) {
    const id = pick();
    const res = http.get(`${target}/products/${id}`, { tags: { name: "product" } });
    productLatency.add(res.timings.duration);
    productFailed.add(res.status !== 200);
    check(res, { "product 200": (r) => r.status === 200 });
    if (alsoBought) {
      const user = 1 + Math.floor(Math.random() * 2000);
      const box = http.get(`${target}/products/${id}/also-bought?user_id=${user}`, {
        tags: { name: "also_bought" },
      });
      check(box, { "also bought 200": (r) => r.status === 200 });
    }
  } else if (roll < 0.95) {
    const term = searchTerms[Math.floor(Math.random() * searchTerms.length)];
    const res = http.get(`${target}/products?q=${encodeURIComponent(term)}&limit=10`, {
      tags: { name: "search" },
    });
    check(res, { "search 200": (r) => r.status === 200 });
  } else {
    const res = http.post(
      `${target}/orders`,
      JSON.stringify({ user_id: 1 + Math.floor(Math.random() * 2000), product_id: pick(), quantity: 1 }),
      { headers: { "Content-Type": "application/json" }, tags: { name: "order" } },
    );
    check(res, { "order 201": (r) => r.status === 201 });
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
    // Product pages alone (the path most shoppers are on).
    product_p99_ms: metric("product_latency").values?.["p(99)"] ?? null,
    product_error_rate: metric("product_failed").values?.rate ?? null,
    requests: metric("http_reqs").values?.count ?? 0,
    thresholds_passed: Object.values(data.metrics).every(
      (m) => !m.thresholds || Object.values(m.thresholds).every((t) => t.ok),
    ),
  };
  return { stdout: JSON.stringify(out) + "\n" };
}
