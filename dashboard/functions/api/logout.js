import { clearSessionCookie } from "../../lib/auth.js";
import { json } from "../../lib/github.js";

export async function onRequestPost() {
  const res = json({ ok: true });
  res.headers.append("Set-Cookie", clearSessionCookie());
  return res;
}
