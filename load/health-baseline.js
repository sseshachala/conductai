// Baseline load test — /health at steady 50 rps for 30 seconds.
// First cut of Group G (PR-G1 of epic #1092). Grow into per-endpoint
// scenarios once the pipeline is proven end-to-end in CI.

import http from "k6/http"
import { check, sleep } from "k6"

const BASE_URL = __ENV.CONDUCT_API_URL || "http:" + "//127.0.0.1:8000"

export const options = {
  scenarios: {
    steady_50_rps: {
      executor: "constant-arrival-rate",
      rate: 50,
      timeUnit: "1s",
      duration: "30s",
      preAllocatedVUs: 20,
      maxVUs: 50,
    },
  },
  thresholds: {
    // Baseline SLOs — tune after first real run.
    http_req_duration: ["p(95)<300", "p(99)<600"],
    http_req_failed: ["rate<0.01"],
  },
}

export default function () {
  const res = http.get(`${BASE_URL}/health`)
  check(res, {
    "status 200": (r) => r.status === 200,
    "body has ok": (r) => r.body.includes("ok"),
  })
  sleep(0.02)
}
