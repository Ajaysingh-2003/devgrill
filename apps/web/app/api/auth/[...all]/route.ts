import { toNextJsHandler } from "better-auth/next-js";
import { auth } from "@/lib/auth";

// Better Auth: sign-in, OAuth callbacks (/api/auth/callback/github), sessions, /token, /jwks.
export const { GET, POST } = toNextJsHandler(auth);
