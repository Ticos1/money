// Acesso ao repositório pelo token do GitHub (variável GITHUB_TOKEN no Cloudflare).
// O estado (fila, configurações) fica em arquivos JSON no próprio repositório.

function toBase64(text) {
  const bytes = new TextEncoder().encode(text);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function fromBase64(b64) {
  const bin = atob(b64.replace(/\n/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

export class GitHub {
  constructor(env) {
    if (!env.GITHUB_TOKEN || !env.GITHUB_REPO) throw new Error("Configure GITHUB_TOKEN e GITHUB_REPO no Cloudflare");
    this.token = env.GITHUB_TOKEN;
    this.repo = env.GITHUB_REPO;
    this.branch = env.GITHUB_BRANCH || "main";
    this.api = env.GITHUB_API_URL || "https://api.github.com"; // trocável só para testes locais
  }

  async call(path, init = {}) {
    const res = await fetch(`${this.api}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.token}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "painel-conteudo-cristao",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
      },
    });
    return res;
  }

  async getJson(path, fallback = null) {
    const res = await this.call(`/repos/${this.repo}/contents/${path}?ref=${this.branch}`);
    if (res.status === 404) return { data: fallback, sha: null };
    if (!res.ok) throw new Error(`GitHub ${res.status} ao ler ${path}`);
    const meta = await res.json();
    let content = meta.content;
    if (!content) {
      // arquivos > 1 MB vêm sem conteúdo: busca pelo blob
      const blob = await this.call(`/repos/${this.repo}/git/blobs/${meta.sha}`);
      content = (await blob.json()).content;
    }
    return { data: JSON.parse(fromBase64(content)), sha: meta.sha };
  }

  // Vários arquivos numa chamada só (GraphQL). files = { nome: [caminho, padrão] }.
  // Se o GraphQL falhar (ou o arquivo for grande demais para ele), lê aquele arquivo pela API REST.
  async getMany(files) {
    const names = Object.keys(files);
    const result = {};
    let repo = null;
    try {
      const [owner, name] = this.repo.split("/");
      const vars = { owner, name };
      const fields = names.map((n, i) => {
        vars[`e${i}`] = `${this.branch}:${files[n][0]}`;
        return `f${i}: object(expression: $e${i}) { ... on Blob { oid text isTruncated } }`;
      });
      const decl = names.map((_, i) => `$e${i}: String!`).join(", ");
      const res = await this.call("/graphql", { method: "POST", body: JSON.stringify({
        query: `query($owner: String!, $name: String!, ${decl}) { repository(owner: $owner, name: $name) { ${fields.join(" ")} } }`,
        variables: vars,
      }) });
      const out = res.ok ? await res.json() : {};
      // qualquer erro (ex.: token sem acesso ao GraphQL): melhor ler pela REST do que achar que o arquivo sumiu
      repo = out.errors?.length ? null : out.data?.repository || null;
    } catch {
      repo = null;
    }
    await Promise.all(names.map(async (n, i) => {
      const [path, fallback] = files[n];
      const blob = repo ? repo[`f${i}`] : undefined;
      if (repo && blob === null) result[n] = { data: fallback, sha: null }; // arquivo não existe
      else if (blob?.text != null && !blob.isTruncated) result[n] = { data: JSON.parse(blob.text), sha: blob.oid };
      else result[n] = await this.getJson(path, fallback);
    }));
    return result;
  }

  async putJson(path, data, sha, message) {
    const body = {
      message,
      content: toBase64(JSON.stringify(data, null, 1) + "\n"),
      branch: this.branch,
      ...(sha ? { sha } : {}),
    };
    return this.call(`/repos/${this.repo}/contents/${path}`, { method: "PUT", body: JSON.stringify(body) });
  }

  // Lê, altera e grava; se alguém (ex.: o GitHub Actions) gravou no meio, tenta de novo.
  async update(path, fallback, mutate, message) {
    for (let attempt = 0; attempt < 4; attempt++) {
      const { data, sha } = await this.getJson(path, fallback);
      const result = mutate(data);
      const res = await this.putJson(path, data, sha, message);
      if (res.ok) return result;
      if (res.status !== 409 && res.status !== 422) throw new Error(`GitHub ${res.status} ao gravar ${path}`);
      await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
    }
    throw new Error("Conflito ao salvar, tente de novo");
  }

  async dispatch(inputs, workflow = "pipeline.yml") {
    const res = await this.call(`/repos/${this.repo}/actions/workflows/${workflow}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: this.branch, inputs }),
    });
    if (!res.ok) throw new Error(`Não consegui iniciar o GitHub Actions (${res.status}). O token tem permissão "Actions: Read and write"?`);
  }
}

export function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}
