# Publicação automática: como ativar

Depois de configurado, o fluxo é este: **você aprova no painel → o sistema
publica sozinho no horário do post** (ou na hora, se o horário já passou).
Uma rotina roda de hora em hora (das 05:07 às 23:07) e publica o que estiver
aprovado e no horário.

| Rede | O que é publicado | Situação |
|---|---|---|
| Instagram | Versículo → foto 4:5 no feed · Quiz → Reels (com música) | ✅ funciona logo após configurar |
| Facebook (Página) | Versículo → foto · Quiz → vídeo | ✅ funciona logo após configurar |
| YouTube Shorts | Quiz (vídeo) | ⚠️ funciona, mas fica **privado** até a auditoria do YouTube |
| TikTok | — | precisa da auditoria do app no TikTok (próxima etapa) |
| Kwai | — | sem API pública: continua manual |

> Se você ativar **"Aprovar automaticamente"** em Configurações, nem a aprovação
> é necessária: o sistema gera e publica 100% sozinho.

---

## Passo 1: senha dos links de mídia (uma vez só)

O Instagram e o Facebook precisam **baixar** a imagem ou o vídeo do seu
painel, que é protegido por senha. Para isso, o sistema cria links
temporários assinados (valem 3 horas).

1. Invente uma sequência aleatória de **40 ou mais caracteres**, só com letras
   e números (ex.: `h7Kq2mZp9...`).
2. **GitHub** → Settings → Secrets and variables → Actions → *New repository secret*
   - Name: `MEDIA_SIGNING_SECRET` · Secret: a sequência
3. **Cloudflare** → Workers & Pages → `palavra-diaria` → Settings → Variables and Secrets → *Add*
   - Name: `MEDIA_SIGNING_SECRET` · Tipo: Secret · Valor: **a mesma sequência**
4. No GitHub: **Actions → Pipeline de conteúdo → Run workflow → mode `deploy`**,
   para o painel passar a reconhecer os links.

---

## Passo 2: Instagram e Facebook (Meta)

### 2.1 Pré-requisitos
- Instagram **profissional** (conta de **Criador** ou Empresa). No app do
  Instagram: Configurações → *Tipo de conta e ferramentas* → *Mudar para conta
  profissional*. Prefira **Criador**: contas Empresa têm menos músicas na
  biblioteca do app.
- Uma **Página do Facebook** conectada a esse Instagram: na Página, vá em
  Configurações → *Contas vinculadas* → Instagram → *Conectar*.

### 2.2 Criar o app de desenvolvedor (grátis)
> Dica: no celular, use o navegador no modo **"Site para computador"**.

1. Acesse <https://developers.facebook.com> → **Começar** (confirme seu cadastro de desenvolvedor).
2. **Meus apps → Criar app**.
3. Caso de uso: **Outro** → Tipo de app: **Empresa** → nome: `Palavra Diaria Publicador` → **Criar app**.
4. Não precisa enviar o app para análise da Meta. Em **modo de desenvolvimento**
   ele funciona para você, que é o administrador.

### 2.3 Gerar o token que não expira
1. Abra o **Explorador da Graph API**: <https://developers.facebook.com/tools/explorer>
2. Em **Meta App**, escolha `Palavra Diaria Publicador`.
3. Em **User or Page**, escolha **Get User Access Token**.
4. Em **Permissions**, adicione:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `instagram_basic`, `instagram_content_publish`, `business_management`
5. Toque em **Generate Access Token**, faça login e **marque a sua Página e o seu Instagram**.
6. Copie o token gerado e abra o **Depurador de token**:
   <https://developers.facebook.com/tools/debug/accesstoken>
   → cole → **Debug** → no fim da página, **Extend Access Token** → copie o novo token (longa duração).
7. Volte ao Explorador, cole esse token longo no campo *Access Token* e consulte:
   `me/accounts?fields=name,access_token,instagram_business_account` → **Submit**.
8. Na resposta, copie o `access_token` da sua Página.
   - Confira no Depurador: deve aparecer **Expires: Never**.
   - O `instagram_business_account` precisa aparecer na resposta. Se não aparecer, o Instagram não está conectado à Página.

### 2.4 Guardar no GitHub
**Settings → Secrets and variables → Actions → New repository secret**
- Name: `META_ACCESS_TOKEN` · Secret: o token da Página (passo 2.3.8)

### 2.5 Ligar no painel
Painel → **Configurações** → marque **Instagram** e **Facebook** → **Salvar**.

---

## Passo 3: YouTube Shorts (opcional)

### 3.1 Projeto no Google Cloud (grátis)
1. <https://console.cloud.google.com> → crie o projeto `palavra-diaria`.
2. **APIs e serviços → Biblioteca → YouTube Data API v3 → Ativar**.
3. **Google Auth Platform / Tela de consentimento OAuth**:
   - Tipo **Externo**, nome do app, seu e-mail.
   - Em **Público-alvo**, toque em **Publicar app** (modo produção). Em modo
     "Teste", o acesso expira a cada 7 dias.
4. **Credenciais → Criar credenciais → ID do cliente OAuth → Aplicativo da Web**
   - *URIs de redirecionamento autorizados*: `https://developers.google.com/oauthplayground`
   - Copie o **ID do cliente** e a **Chave secreta**.

### 3.2 Pegar o "refresh token"
1. Abra <https://developers.google.com/oauthplayground>
2. Toque na **engrenagem ⚙** → marque **Use your own OAuth credentials** → cole o ID e a chave.
3. Em *Step 1*, digite o escopo `https://www.googleapis.com/auth/youtube.upload` → **Authorize APIs**.
4. Entre com a conta do **canal**. Se aparecer "app não verificado", toque em
   *Avançado → Acessar* (o app é seu).
5. Em *Step 2*, toque em **Exchange authorization code for tokens** e copie o **Refresh token**.

### 3.3 Guardar no GitHub (Secrets)
`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`

### 3.4 Ligar no painel
Configurações → marque **YouTube Shorts** → Salvar.

⚠️ **Os vídeos vão ficar privados** até o projeto passar pela auditoria do
YouTube (regra para projetos criados depois de 2020). O link aparece no painel
e você pode mudar para *Público* no YouTube Studio. O pedido de auditoria está
em [FASES.md](FASES.md#fase-2-youtube-shorts-youtube-data-api-v3).

---

## Testar
1. No painel, aprove um post cujo horário já passou.
2. Em 1 a 3 minutos, aparece em **"Onde já publiquei"**: ✅ com o link **"ver post ↗"**,
   ou o **erro** em vermelho, explicando o que corrigir.
3. Também dá para forçar pelo GitHub: **Actions → Publicar nas redes → Run workflow**.

Se uma rede der erro, ela é tentada de novo nas próximas horas (até 3 vezes).
Depois de corrigir a configuração, desmarque e marque de novo, ou rode o workflow.

## Limites (todos grátis)
- Instagram: até 50 posts por API a cada 24 h (usamos 1 a 2).
- GitHub Actions: a rotina de hora em hora usa cerca de 10 min/dia, que somados à
  geração ficam bem abaixo dos 2.000 min/mês grátis.

---

## Agendador confiável (Cloudflare) — importante

O agendamento do GitHub Actions **atrasa e pula execuções** em horários de muito
uso. Por isso, quem dispara a publicação no horário é um pequeno **Worker do
Cloudflare** (`scheduler/`), que roda a cada 5 minutos, de graça. Ele também
garante a geração diária, se a das 05:17 não rodar.

Configuração (uma vez):
1. **Permissão do token:** Cloudflare → My Profile → API Tokens → edite o token
   usado pelo GitHub → **Add more** → `Account` · `Workers Scripts` · `Edit` → Save.
2. Rode **Actions → Pipeline de conteúdo → mode `deploy`**. Isso instala o Worker `palavra-diaria-agendador`.
3. **Cloudflare → Workers & Pages → `palavra-diaria-agendador` → Settings → Variables and Secrets → Add:**
   - Tipo **Secret** · Name `GITHUB_TOKEN` · Value: o mesmo token `github_pat_...` usado no painel.

---

## Métricas (aba "Métricas" do painel)

As métricas são coletadas a cada publicação e a cada 3 horas: curtidas e
comentários (Instagram e Facebook) e visualizações (YouTube). O painel mostra a
média por **tipo de post** e por **horário**, além do **Top 10**, para você
descobrir o que funciona melhor.

Para ver também **alcance, salvamentos e compartilhamentos** do Instagram, gere
o token da Meta (parte C) adicionando a permissão `instagram_manage_insights` e
atualize o segredo `META_ACCESS_TOKEN`.

Para ver as **visualizações dos Shorts**, gere o refresh token do YouTube no
OAuth Playground com os dois escopos (separados por espaço):
`https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly`
e atualize o segredo `YT_REFRESH_TOKEN`.
