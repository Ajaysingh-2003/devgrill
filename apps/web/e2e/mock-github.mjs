// A stand-in for GitHub's OAuth and REST endpoints, for end-to-end tests (ADR 011).
// Implements exactly what lib/auth-config.mts uses:
//   GET  /login/oauth/authorize     -> redirects straight back with a code (auto-consent)
//   POST /login/oauth/access_token  -> exchanges the code for an access token
//   GET  /user, GET /user/emails    -> the profile of whoever that token belongs to
// Who signs in: the `mock_user` cookie on the authorize request (each Playwright context has
// its own cookies, so parallel tests don't collide), else the default user.
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const PORT = Number(process.env.MOCK_GITHUB_PORT ?? 3999);
const DEFAULT_USER = { id: 1001, login: "octo-tester", name: "Octo Tester", email: "octo@example.test" };

/** A stable fake GitHub user for a login (same login -> same numeric id). */
function userFromLogin(login) {
  let id = 0;
  for (const ch of login) id = (id * 31 + ch.charCodeAt(0)) % 1_000_000_007;
  return { id, login, name: login.replace(/-/g, " "), email: `${login}@example.test` };
}

function cookieUser(req) {
  const match = /(?:^|;\s*)mock_user=([^;]+)/.exec(req.headers.cookie ?? "");
  return match ? userFromLogin(decodeURIComponent(match[1])) : DEFAULT_USER;
}
const codes = new Map(); // code -> user
const tokens = new Map(); // access token -> user

const json = (res, status, body) => {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
};

const readBody = (req) =>
  new Promise((resolve) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => resolve(data));
  });

const parseBody = (raw, type = "") => {
  if (type.includes("application/json")) return JSON.parse(raw || "{}");
  return Object.fromEntries(new URLSearchParams(raw));
};

const userFor = (req) => tokens.get((req.headers.authorization ?? "").replace(/^(Bearer|token) /i, ""));

createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);

  if (url.pathname === "/__mock/health") return json(res, 200, { ok: true });

  if (url.pathname === "/login/oauth/authorize") {
    const redirect = url.searchParams.get("redirect_uri");
    if (!redirect) return json(res, 400, { error: "redirect_uri required" });
    const code = randomBytes(12).toString("hex");
    codes.set(code, cookieUser(req));
    const back = new URL(redirect);
    back.searchParams.set("code", code);
    back.searchParams.set("state", url.searchParams.get("state") ?? "");
    res.writeHead(302, { location: back.toString() });
    return res.end();
  }

  if (url.pathname === "/login/oauth/access_token" && req.method === "POST") {
    const body = parseBody(await readBody(req), req.headers["content-type"]);
    const user = codes.get(body.code);
    if (!user) return json(res, 400, { error: "bad_verification_code" });
    codes.delete(body.code);
    const token = `gho_${randomBytes(16).toString("hex")}`;
    tokens.set(token, user);
    return json(res, 200, { access_token: token, token_type: "bearer", scope: "read:user,user:email" });
  }

  if (url.pathname === "/user") {
    const user = userFor(req);
    if (!user) return json(res, 401, { message: "Bad credentials" });
    return json(res, 200, {
      id: user.id,
      login: user.login,
      name: user.name,
      email: user.email,
      avatar_url: null,
    });
  }

  if (url.pathname === "/user/emails") {
    const user = userFor(req);
    if (!user) return json(res, 401, { message: "Bad credentials" });
    return json(res, 200, [{ email: user.email, primary: true, verified: true }]);
  }

  json(res, 404, { message: "Not Found" });
}).listen(PORT, () => console.log(`mock GitHub on http://localhost:${PORT}`));
