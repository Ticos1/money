# Passo a passo para colocar no ar (tudo grátis)

Tempo total: cerca de **30 minutos**, uma vez só. Ao final você terá:

- os posts sendo gerados **sozinhos todo dia**;
- o painel em `https://SEU-PROJETO.pages.dev`, protegido por senha.

Você vai criar **3 contas** (GitHub, Groq e Cloudflare) e colar **algumas chaves**.
Nenhuma pede cartão de crédito.

> 🔐 **Regra de ouro:** chaves e senhas **nunca** vão no código. Elas ficam só
> em "Secrets" do GitHub e em "Variáveis e segredos" do Cloudflare.

---

## Parte 1: GitHub (onde o código roda)

Você já tem a conta e o repositório `money`.

### 1.1 Deixar o repositório **privado** (recomendado)

Em **Settings → General → Danger Zone → Change visibility → Private**.

Por que privado?
- O plano grátis dá **2.000 minutos/mês** de Actions para repositórios privados.
  O sistema usa cerca de **120 a 200 minutos/mês** (4 a 6 min por dia).
- Com o repositório público, qualquer pessoa veria o seu banco de conteúdo, a
  fila de posts ainda não publicados e os vídeos.
- As chaves ficam protegidas nos dois casos, porque os Secrets nunca aparecem.

### 1.2 Juntar este trabalho na branch principal

O código está na branch `claude/admiring-hypatia-5mc8ck`. O agendamento diário só
funciona na branch principal (`main`). Abra um *Pull Request* dessa branch para
a `main` e clique em **Merge** (se quiser, eu abro o PR para você).

### 1.3 Permitir que o Actions grave no repositório

**Settings → Actions → General → Workflow permissions → "Read and write permissions" → Save.**

### 1.4 Criar o token do painel (para ele aprovar e editar posts)

1. Acesse <https://github.com/settings/personal-access-tokens/new> (*Fine-grained token*).
2. **Token name:** `painel-conteudo` · **Expiration:** 1 ano (anote para renovar).
3. **Repository access:** *Only select repositories* → `money`.
4. **Permissions → Repository permissions:**
   - **Contents:** Read and write
   - **Actions:** Read and write
5. **Generate token** e **copie** o valor (`github_pat_...`). Ele aparece só uma vez.
   Guarde-o para a Parte 3.

---

## Parte 2: Groq (IA grátis, opcional mas recomendado)

1. Acesse <https://console.groq.com> e crie a conta (Google, GitHub ou e-mail).
2. Menu **API Keys → Create API Key** → nome `palavra-diaria` → **copie** a chave (`gsk_...`).
3. No GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GROQ_API_KEY` · Secret: *cole a chave*.

**Sobre o plano grátis:**
- Não cobra nada. Quando o limite acaba, a API só responde "limite atingido", e o
  sistema usa o banco.
- Os limites por modelo ficam em <https://console.groq.com/settings/limits>. O
  sistema usa no máximo **6 chamadas por dia** (configurável no painel).
- **Uso comercial:** o contrato da Groq (*Services Agreement*) é voltado a
  desenvolvedores e empresas e permite integrar a API em produtos. O conteúdo
  gerado é seu. Ele proíbe revender o serviço e tentar burlar limites para não
  pagar, e nada disso acontece aqui. Cada modelo tem termos próprios. O modelo
  padrão (`openai/gpt-oss-120b`) é de licença aberta Apache 2.0.
- **Modelo:** o padrão é o `openai/gpt-oss-120b` (o melhor em português entre os
  de produção), com reserva `llama-3.3-70b-versatile`. Dá para trocar no painel
  → Configurações.

---

## Parte 3: Cloudflare (painel no ar)

### 3.1 Criar a conta

<https://dash.cloudflare.com/sign-up>: grátis, sem cartão.

### 3.2 Criar o projeto do painel (Pages)

1. No menu: **Workers & Pages → Create → Pages → Upload assets** (*direct upload*).
2. **Project name:** por exemplo `palavra-diaria`. O endereço será `palavra-diaria.pages.dev`.
3. Ele pede um primeiro upload: envie qualquer arquivo (por exemplo, um
   `index.html` vazio). O GitHub Actions vai substituir pelo painel de verdade.
4. Anote o nome do projeto.

### 3.3 Variáveis do painel (senha e acesso ao GitHub)

No projeto: **Settings → Variables and Secrets → Add** (em *Production*):

| Nome | Tipo | Valor |
|---|---|---|
| `DASHBOARD_PASSWORD` | Secret | a senha que você vai usar para entrar (longa!) |
| `SESSION_SECRET` | Secret | 40+ caracteres aleatórios (gere num gerenciador de senhas) |
| `GITHUB_TOKEN` | Secret | o token `github_pat_...` da Parte 1.4 |
| `GITHUB_REPO` | Text | `Ticos1/money` |
| `GITHUB_BRANCH` | Text | `main` |

### 3.4 Chave para o GitHub publicar o painel

1. Clique no seu perfil (canto superior direito) → **My Profile → API Tokens → Create Token**.
2. Escolha **Create Custom Token**:
   - **Permissions:** `Account` · `Cloudflare Pages` · `Edit`
   - **Account Resources:** Include · *sua conta*
3. **Continue → Create Token** → **copie** o token.
4. Pegue também o **Account ID**: em **Workers & Pages**, ele aparece na lateral
   direita (ou na URL do painel: `dash.cloudflare.com/<ACCOUNT_ID>/...`).

No GitHub: **Settings → Secrets and variables → Actions**:
- aba **Secrets**: `CLOUDFLARE_API_TOKEN` (o token) e `CLOUDFLARE_ACCOUNT_ID` (o ID);
- aba **Variables**: `CF_PAGES_PROJECT` = `palavra-diaria` (o nome do projeto).

### 3.5 (Opcional) Camada extra: Cloudflare Access

O painel já tem login por senha. Se quiser uma segunda trava (login por código
no seu e-mail):

1. **Zero Trust → Access → Applications → Add → Self-hosted**.
2. Domínios: `palavra-diaria.pages.dev` **e** `*.palavra-diaria.pages.dev`
   (este último cobre os endereços de prévia).
3. Policy: **Allow** · *Emails* · o seu e-mail.

O plano Zero Trust é grátis para até 50 usuários, mas o Cloudflare pode pedir
um **cartão cadastrado** (sem cobrança) para ativá-lo. Como você não quer
cadastrar cartão, pode pular esta etapa: a senha do painel já protege tudo.

---

## Parte 4: Primeira geração

1. No GitHub: **Actions → "Pipeline de conteúdo" → Run workflow** → mode `generate` → **Run**.
2. Espere de 4 a 6 minutos (dá para acompanhar os passos ficando verdes ✅).
3. Abra `https://palavra-diaria.pages.dev` no celular → digite a senha.
4. Vá em **Configurações** e coloque o seu **@** (vai como marca d'água) e os horários.
   > A marca d'água entra nos posts **a partir da próxima geração**. Para refazer
   > os de hoje: Actions → Run workflow → `generate` com `force = true`.

**Dica:** no celular, use "Adicionar à tela inicial" para o painel virar um ícone.

A partir daí, **todo dia às 05:17** os posts novos aparecem sozinhos na fila.

---

## Como baixar os vídeos no celular

- **Android:** toque em "⬇ Vídeo…". O arquivo vai para *Downloads* e aparece na galeria.
- **iPhone:** toque em "⬇ Vídeo…" → o vídeo abre → botão **Compartilhar** → **Salvar vídeo**.

## Problemas comuns

| Sintoma | Solução |
|---|---|
| Painel mostra "Painel ainda não configurado" | Falta `DASHBOARD_PASSWORD` ou `SESSION_SECRET` (mínimo 32 caracteres) no Cloudflare. Depois de adicionar, rode o workflow com mode `deploy`. |
| Painel mostra erro do GitHub | Confira `GITHUB_TOKEN` (permissões Contents e Actions: Read and write) e `GITHUB_REPO`. |
| "Gerar agora" dá erro | O token precisa da permissão **Actions: Read and write**. |
| Workflow falha no passo "Publicar painel" | Confira `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` e `CF_PAGES_PROJECT` (nome exato). |
| Workflow falha em "Salvar estado" | Parte 1.3: permissão *Read and write* do Actions. |
| Post com aviso vermelho "Edição inválida" | A resposta editada do quiz não aparece no versículo. Ajuste a edição. |
| Nada novo gerado | Os posts do dia já existiam. Use `force = true` para refazer. |
