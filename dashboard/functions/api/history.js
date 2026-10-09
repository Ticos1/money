import { GitHub, json } from "../../lib/github.js";

export async function onRequestGet({ env }) {
  try {
    const { data } = await new GitHub(env).getJson("state/history.json", { posts: [] });
    return json({ posts: data.posts });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
