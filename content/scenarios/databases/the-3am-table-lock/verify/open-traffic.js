// ShopKart's traffic mix arriving at a fixed rate, whatever is stuck (an open model). With a
// fixed set of virtual users, every user blocked on a locked checkout stops sending anything,
// and the outage hides itself; real shoppers keep arriving. Same summary line as shop.js.
import shop, { handleSummary } from "../load/shop.js";

export { handleSummary };

export const options = {
  scenarios: {
    open: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 150),
      timeUnit: "1s",
      duration: __ENV.DURATION || "40s",
      preAllocatedVUs: 100,
      maxVUs: 500,
    },
  },
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
};

export default shop;
