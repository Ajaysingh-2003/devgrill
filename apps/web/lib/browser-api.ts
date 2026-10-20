import { createClient, createConfig, type Client, type Problem } from "@devgrill/api-client";

/** A refused or failed API call from the browser, with the problem's code and Retry-After. */
export class ProblemError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
    readonly retryAfter: number | null,
    message: string,
    /** The problem's `instance`: for a conflict, the resource it conflicts with. */
    readonly instance: string | null = null,
  ) {
    super(message);
    this.name = "ProblemError";
  }
}

let client: Client | null = null;

/**
 * The generated client for client components. It calls the same-origin proxy (/api/v1/...),
 * which adds the caller's credentials on the server: the browser never holds the API token.
 */
export function browserApi(): Client {
  client ??= createClient(createConfig({ baseUrl: `${window.location.origin}/api`, cache: "no-store" }));
  return client;
}

type Result<T> = { data?: T; error?: unknown; response?: Response };

/** Unwrap a generated-client call, or throw a ProblemError with the API's own words. */
export async function call<T>(request: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await request;
  } catch {
    throw new ProblemError(0, "network", null, "Can't reach DevGrill. Check your connection.");
  }
  const { data, error, response } = result;
  if (response?.ok) return data as T;
  const problem = (error ?? null) as Problem | null;
  const retry = response?.headers.get("retry-after");
  throw new ProblemError(
    response?.status ?? 0,
    problem?.code ?? null,
    retry ? Number(retry) : null,
    problem?.detail ?? problem?.title ?? "Something went wrong.",
    problem?.instance ?? null,
  );
}
