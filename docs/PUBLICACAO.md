# Publicação automática: como ativar

Depois de configurado, o fluxo é este: **você aprova no painel → o sistema
publica sozinho no horário do post** (ou na hora, se o horário já passou).
Uma rotina roda de hora em hora (das 05:07 às 23:07) e publica o que estiver
aprovado e no horário.

**Variação de horário:** cada post sai até **10 minutos antes ou depois** do horário
da grade (ex.: o das 08:00 pode sair às 07:53 ou às 08:06), sorteado na geração, para
não parecer automação. O painel mostra o horário real. Ajuste em
`publishing.time_jitter_minutes` no `config/settings.json` (0 desliga).

| Rede | O que é publicado | Situação |
|---|---|---|
| Instagram | Versículo → foto 4:5 no feed · Quiz → Reels (com música) | ✅ funciona logo após configurar |
| Facebook (Página) | Versículo → foto · Quiz → vídeo | ✅ funciona logo após configurar |
| YouTube Shorts | Quiz (vídeo) | ⚠️ funciona, mas fica **privado** até a auditoria do YouTube |
| TikTok | — | precisa da auditoria do app no TikTok (próxima etapa) |
| Kwai | — | sem API pública: continua manual |
| Canal do WhatsApp | — | sem API oficial para canais: manual pelo botão 📲 do painel ([WHATSAPP.md](WHATSAPP.md)) |

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
comentários (Instagram e Facebook), visualizações (YouTube) e, nos vídeos do Facebook,
visualizações, views de 3 s, quantos assistiram até o fim e o **tempo médio assistido**
(o quadro *Vídeos que prendem a atenção* mostra quais seguram mais o público). O painel mostra a
média por **tipo de post** e por **horário**, além do **Top 10**, para você
descobrir o que funciona melhor.

### Liberar as métricas completas (passo a passo)

**A) Instagram (alcance, salvamentos) e Facebook (views e tempo médio dos vídeos)** (cerca de 5 min)
1. Abra <https://developers.facebook.com/tools/explorer> (no celular, use "Site para computador").
2. **Meta App:** `Palavra Diaria Publicador` · **User or Page:** *Get User Access Token*.
3. Em **Permissions**, deixe as que já usava e **adicione** `instagram_manage_insights` e `read_insights`:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management`, `instagram_manage_insights`, `read_insights`
4. **Generate Access Token** → confirme a sua Página e o seu Instagram.
5. Copie o token → abra <https://developers.facebook.com/tools/debug/accesstoken> → cole →
   **Debug** → **Extend Access Token** → copie o token longo.
6. Volte ao Explorador, cole o token longo e consulte
   `me/accounts?fields=name,access_token,instagram_business_account` → **Submit**.
7. Copie o `access_token` da Página (no Depurador deve aparecer **Expires: Never**).
8. GitHub → Settings → Secrets and variables → Actions → `META_ACCESS_TOKEN` → **Update** → cole → Save.

**B) YouTube: visualizações dos Shorts** (cerca de 3 min)
1. Abra <https://developers.google.com/oauthplayground>.
2. Engrenagem ⚙ → marque **Use your own OAuth credentials** → cole o mesmo ID do cliente e a chave secreta de antes.
3. Em *Step 1*, apague o que estiver na caixa e cole os dois escopos (com um espaço entre eles):
   `https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly`
   → **Authorize APIs**.
4. Entre com a conta do **canal**. Se aparecer "app não verificado": *Avançado → Acessar*. Marque as duas permissões.
5. *Step 2* → **Exchange authorization code for tokens** → copie o **Refresh token**.
6. GitHub → Secrets → `YT_REFRESH_TOKEN` → **Update** → cole → Save.

**C) Conferir**
Painel → **Métricas** → **↻ Atualizar métricas** → espere cerca de 1 minuto e recarregue.
Os avisos amarelos somem e aparecem as colunas de alcance e as visualizações.
Os gráficos mostram o engajamento por dia e a média por horário (toque numa barra para ver o número).

---

## Vídeo longo de quiz no YouTube (~10 minutos)

Toda semana o sistema monta sozinho **um vídeo horizontal (16:9) com cerca de 40 perguntas do
quiz**, com música de fundo, contagem regressiva e a resposta de cada pergunta. Ele sai **só no
YouTube**, como vídeo normal (não é Short), com **miniatura** e **capítulos** na descrição
(0:00 Introdução, 0:07 Pergunta 1, ...). Vídeos longos costumam dar mais tempo de exibição, que é o
que o YouTube mais valoriza.

- **Quando:** sábado ao meio-dia (12:00) (muda em Configurações → *Vídeo longo de quiz*: dia, horário e minutos).
- **De onde vêm as perguntas:** primeiro os quizzes dos últimos 14 dias; o que faltar vem do banco.
  Uma pergunta não volta a um vídeo longo por 90 dias.
- **Onde aparece:** na aba **Fila**, como "Vídeo longo de quiz (YouTube)". Com *Aprovar
  automaticamente* ligado, ele é publicado sozinho no horário.
- **Gerar agora:** Configurações → *Gerar vídeo longo agora* (leva uns 12 a 20 minutos), ou
  GitHub → Actions → *Pipeline de conteúdo* → Run workflow → mode `compilation`.
- **Se der erro:** a geração diária dos posts continua normalmente; o aviso fica no log do Actions.

Observações:
- A **miniatura personalizada** só é aceita pelo YouTube em canais **verificados** (youtube.com/verify,
  é só confirmar o telefone). Sem isso, o vídeo sai igual, com uma miniatura escolhida pelo YouTube.
- A miniatura (`miniatura.jpg`) segue as regras da seção [Capas e títulos do YouTube](#capas-e-títulos-do-youtube).
- Cada envio ao YouTube gasta 1.600 dos 10.000 pontos diários da cota gratuita da API. Com 4 Shorts
  por dia, o vídeo longo cabe (4 × 1.600 + 1.600 = 8.000). Evite várias publicações manuais no mesmo dia.

---

## Token da Meta com erro 190 ("Any of the pages_read_engagement... permission(s) must be granted")

Acontece quando o `META_ACCESS_TOKEN` foi gerado **sem as permissões da Página**. No Explorador da
Graph API, ao gerar um token novo, as permissões marcadas antes **não ficam salvas**: é preciso
marcar todas de novo, não só a que você quer acrescentar.

1. Explorador (<https://developers.facebook.com/tools/explorer>) → Meta App `Palavra Diaria Publicador` →
   *Get User Access Token*.
2. Em **Permissions**, confira que as **nove** estão marcadas (se faltar alguma, adicione):
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management`, `instagram_manage_insights`,
   `pages_manage_metadata`, `read_insights`
3. **Generate Access Token** e, na janela da Meta, **marque a Página e o Instagram** (escolha "todas" se aparecer a opção).
4. Depurador (<https://developers.facebook.com/tools/debug/accesstoken>) → **Extend Access Token** → copie o token longo.
5. No Explorador, cole o token longo e consulte
   `me/accounts?fields=name,access_token,instagram_business_account` → copie o `access_token` **da Página**
   (não o token de usuário).
6. GitHub → Secrets → `META_ACCESS_TOKEN` → **Update** → cole → Save.
7. No painel, abra o post que deu erro e toque em **🚀 Publicar agora** (isso libera nova tentativa;
   sozinho ele tenta só 3 vezes).

---

## Alertas por e-mail e resumo semanal (sem custo, sem configurar nada)

- **Alerta de falha:** quando uma publicação dá erro (Instagram, Facebook, YouTube...), o GitHub
  te manda um e-mail de "Publicar nas redes: falhou" com o motivo. Você recebe no primeiro erro e
  quando o sistema desiste (3 tentativas). Para liberar nova tentativa, abra o post no painel e
  toque em **🚀 Publicar agora**.
  Confira em GitHub → Settings → Notifications → *Actions*: deixe ligado "Send notifications for
  failed workflows only".
- **Resumo semanal:** toda segunda-feira, depois das 08:00, o sistema abre uma *issue* chamada
  "Resumo semanal - dd/mm/aaaa" no repositório, marcando você (@). O GitHub avisa por e-mail. O resumo
  traz visualizações, alcance, engajamento por tipo de post, melhor e pior horário e os 3 melhores
  posts com link. (Precisa de *Issues* ligado em Settings → General → Features, que já vem ligado.)

## Vídeo também para "Você sabia?" e Versículo

Em **Configurações → Vídeos (Reels e Shorts)**, marque para o "Você sabia?" e/ou o Versículo
virarem vídeo vertical com música (em vez de só imagem). Eles passam a sair como Reels, Shorts
(YouTube), vídeo no Facebook e Stories. Atenção à cota do YouTube: cada envio gasta 1.600 dos 10.000
pontos diários, então 6 vídeos por dia (4 quizzes + 2 curiosidades) já usam 9.600, e o vídeo longo de
sábado passaria do limite. Se quiser os dois, peça o aumento de cota (gratuito) no Google Cloud.

## Capas e títulos do YouTube

Nos Shorts e no vídeo longo, o que faz a pessoa clicar é a **capa** e o **título**. O sistema cria
os dois sozinho:

**Capa com texto grande** (`app/render/cover.py`)
- **Short** (`capa_youtube.jpg`, 1080×1920): selo "QUIZ BÍBLICO", chamada gigante com contorno
  ("SÓ 1% ACERTA", "VERDADE OU MENTIRA?", "COMPLETE O VERSÍCULO"), a pergunta num cartão branco,
  o nível (fácil/médio/difícil) e "VOCÊ SABE?". Tudo fica na faixa do meio, que é o que aparece no
  recorte da busca e da grade do canal. Ela **nunca mostra a resposta**.
- **Vídeo longo** (`miniatura.jpg`, 1280×720): "40 PERGUNTAS" enorme à esquerda, "SÓ 1% ACERTA
  TODAS!" à direita e a faixa "FÁCIL ATÉ DIFÍCIL · 10 MIN" embaixo, longe do canto onde o YouTube
  mostra a duração.
- A publicação automática envia a capa logo depois do vídeo (gasta 50 pontos da cota; 6 Shorts por
  dia continuam cabendo: 6 × 1.650 = 9.900). Exige **canal verificado** (youtube.com/verify). Se o
  YouTube recusar a capa de um Short, o vídeo sai do mesmo jeito e o log diz "miniatura não
  aplicada". Nesse caso, baixe a capa no painel (botão **⬇ Capa do YouTube**) e troque à mão no
  app do YouTube ou no YouTube Studio (editar o vídeo → miniatura), se a opção aparecer na sua conta.

**Título otimizado** (`app/youtube_seo.py`)
- Palavra-chave que as pessoas buscam **no começo** ("Quiz Bíblico:", "Verdadeiro ou falso?",
  "Complete o versículo:").
- Até **70 caracteres**, que aparecem inteiros no celular. Se a pergunta for longa, entra um título
  curto de curiosidade ("Quiz Bíblico (nível difícil 🔥): você acerta essa?").
- A pergunta no título dá curiosidade, mas a **resposta nunca aparece** (há um teste para isso).
- No máximo 1 emoji, sem caixa alta no título inteiro, `#shorts` no final.
- O vídeo vai com **tags** (quiz bíblico, perguntas bíblicas, o livro da Bíblia etc.) e com o idioma
  pt-BR, o que ajuda a busca do YouTube.
- Vídeo longo: `QUIZ BÍBLICO: 40 perguntas (só 1% acerta todas!) | 10 min`.

Exemplos de título:
`Quiz Bíblico: Quantos dias Jonas ficou no ventre do grande peixe? #shorts` ·
`Verdadeiro ou falso? Qual rei edificou o templo (a casa) em Jerusalém? #shorts` ·
`Complete o versículo: 2 Timóteo 1:7 📖 Você sabe de cor? #shorts`

## Limite diário do YouTube (proteção automática)

A cota grátis da API do YouTube é de 10.000 pontos por dia, e cada vídeo enviado gasta 1.600, ou
seja, cabem **6 vídeos por dia**. O sistema conta os envios do dia (horário de Brasília) e, ao chegar
no limite (`publishing.youtube_max_per_day`, padrão 6), **pula** o YouTube nos posts seguintes sem
dar erro: eles saem normalmente nas outras redes e o painel mostra "⏭ pulado: limite...".
Se você pedir aumento de cota ao Google, é só subir esse número em `config/settings.json`.

A agenda padrão tem **9 posts por dia: 1 versículo (imagem) e 8 vídeos**:
06:30 Versículo · 08:00 Quiz · 10:00 Complete o versículo · 12:00 Quiz ·
15:00 Verdadeiro ou falso · 17:00 Quiz · 18:30 Complete o versículo · 20:00 Quiz · 21:30 Verdadeiro ou falso
(até 12 por dia no painel). O "Você sabia?" saiu da agenda em 15/10/2026: em 13 posts teve zero
interação, enquanto o quiz rendeu 1,8× a média. Ele continua disponível para voltar pelo painel.

### Cortar o que não rende: `python -m app.report --analysis`
Compara os formatos nos últimos 28 dias (`--days` muda o período) usando curtidas, comentários,
salvamentos e compartilhamentos do **Instagram e do Facebook**, onde todos os formatos saem (o
YouTube só recebe alguns tipos e distorceria a comparação; as views dele aparecem à parte).
- rende menos da **metade** da média → **cortar**; 30% acima da média → **concentrar**;
- com menos de 30 interações no período, ou menos de 6 posts do formato, não decide nada
  (seria acaso);
- propõe a agenda atual **sem** os horários dos formatos a cortar (menos posts, só os que rendem).
  O Versículo do dia nunca sai por inteiro. `--apply` grava a proposta em `config/settings.json`.

Rode a cada 2 ou 4 semanas, principalmente depois de um formato novo juntar alguns posts.

Todos os vídeos vão para Reels e Stories. Para o **YouTube** vão só os tipos em
`publishing.youtube_types` (padrão: quiz, Complete o versículo e o vídeo longo = 6 por dia, dentro da cota).
Para o **Facebook** vão só os tipos em `publishing.facebook_types` (hoje: quiz, Verdadeiro ou falso e
Você sabia? em vídeo). No Facebook quase todas as visualizações vêm de Reels: o Versículo do dia em
imagem e o Complete o versículo (3 views de média) ficam de fora. Para voltar a mandar tudo, apague a linha.

### Formatos de vídeo
- **Desafio de quiz** — pergunta, 4 alternativas, contagem e resposta.
- **Complete o versículo** — um versículo conhecido do banco com uma palavra escondida e 4 opções.
- **Verdadeiro ou falso?** — uma pergunta do banco com uma resposta mostrada (certa ou errada); o vídeo revela.
- **Você sabia?** — curiosidade bíblica revelada em partes.
Os formatos novos são montados a partir dos bancos já conferidos na Bíblia (nada é inventado).
