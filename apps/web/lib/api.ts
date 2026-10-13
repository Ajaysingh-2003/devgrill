import "server-only";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";
import { createClient, createConfig, type Client, type Problem } from "@devgrill/api-client";
import { getApiToken } from "./auth";

/** An API error that isn't a 404, carrying the RFC 9457 problem for error boundaries. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem: Problem | null,
    readonly requestId: string | null,
  ) {
    super(problem?.detail ?? problem?.title ?? `API error ${status}`);
    this.name = "ApiError";
  }
}

/** One id per page render, sent to the API so web and API logs line up (X-Request-ID). */
const requestId = cache(() => crypto.randomUUID().replaceAll("-", ""));

/** A client for this request: server-to-server base URL, plus the user's JWT if signed in. */
export async function api(): Promise<Client> {
  // API data is per request (and the request id is random): never part of a prerender.
  await connection();
  const token = await getApiToken();
  return createClient(
    createConfig({
      baseUrl: process.env.API_INTERNAL_URL ?? "http://localhost:8000",
      headers: {
        "x-request-id": requestId(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
    }),
  );
}

type Result<T> = { data?: T; error?: unknown; response?: Response };

/**
 * Unwrap a generated-client call: return the data, turn 404 into notFound(), throw ApiError
 * for anything else (the nearest error.tsx shows the problem and the request id).
 */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (data !== undefined && response?.ok) return data;
  const status = response?.status ?? 503;
  if (status === 404) notFound();
  const failure = new ApiError(
    status,
    (error as Problem | undefined) ?? null,
    response?.headers.get("x-request-id") ?? null,
  );
  // Server log: the error boundary only shows a digest, this ties it to the API's logs.
  console.error(`api ${status} ${failure.problem?.code ?? ""} request_id=${failure.requestId}`);
  throw failure;
}

/** "sev2" -> 2, for the SEV glyph components. */
export function sevNumber(difficulty: string): 1 | 2 | 3 | 4 {
  const n = Number(difficulty.replace("sev", ""));
  return (n >= 1 && n <= 4 ? n : 4) as 1 | 2 | 3 | 4;
}
