# Palavra Diária: posts cristãos automáticos

Sistema que **cria sozinho, todo dia**, posts cristãos/evangélicos prontos para
TikTok, Kwai, YouTube Shorts, Instagram e Facebook, e mostra tudo num **painel
no celular** para você aprovar, baixar e copiar a legenda.

Custo: **R$ 0/mês**. Tudo roda em planos gratuitos que permitem uso comercial.

> **Fase 1 (pronta):** geração diária automática de **Versículo do dia** e
> **Desafio de quiz** (vídeo 9:16 + imagens 1:1 e 4:5), com painel para baixar e
> copiar. A postagem nas redes ainda é manual (e segura).
> **Publicação automática** (Instagram, Facebook e YouTube): veja [docs/PUBLICACAO.md](docs/PUBLICACAO.md).
> **TikTok** (Reels nos seus rascunhos do app): veja [docs/TIKTOK.md](docs/TIKTOK.md).
> **Canal do WhatsApp** (legenda própria + botão de enviar no painel): veja [docs/WHATSAPP.md](docs/WHATSAPP.md).

---

## O que o sistema faz todo dia

1. Às **05:20 (Brasília)**, o agendador (Cloudflare Worker) dispara o GitHub Actions, que gera os posts do dia (**10 posts**: 1 Versículo do dia, 4 quizzes, 3 "Verdadeiro ou falso", 1 "Complete o versículo" e 1 "Você sabia?", que sai só no Facebook). A grade está **congelada até 31/10/2026** (`schedule.frozen_until`) para os testes terem dados suficientes: o painel não muda horários, e o repost de domingo e a grade adaptativa estão desligados. O que vai para cada rede: [docs/PUBLICACAO.md](docs/PUBLICACAO.md#o-que-vai-para-cada-rede).
2. Escolhe o conteúdo:
   - **banco próprio** (607 versículos com reflexão, 1.248 perguntas de quiz e 267 curiosidades: o versículo do dia rende mais de um ano; os 6 vídeos de pergunta por dia, cerca de 6 meses só com o banco e mais com o conteúdo novo da IA; veja `python -m app.saturation`);
   - às vezes pede **conteúdo novo à IA (Groq, grátis)**.
3. **Confere toda referência bíblica** contra a Bíblia salva no projeto. Se o livro, capítulo ou versículo não existir, ou se a resposta do quiz não estiver no texto, **descarta**.
4. Monta o **vídeo** com texto animado em **duas versões**:
   - **com música** instrumental livre de direitos (para YouTube e Facebook);
   - **sem música** (para você escolher uma música gospel no próprio TikTok, Kwai ou Instagram).
5. Gera as **imagens** quadrada (1080×1080) e vertical (1080×1350), com a sua marca d'água.
6. Escreve **legendas e hashtags diferentes para cada rede**.
7. Coloca tudo no **painel** (fila), aguardando sua aprovação.

**Datas especiais** (Natal, Sexta-feira Santa, Páscoa, Pentecostes, Dia das Mães, Dia dos Pais, Dia das Crianças, Dia da Reforma, Dia da Bíblia, Ano Novo e domingos): o sistema escolhe conteúdo do tema, com saudação na legenda. Veja `app/datas.py`.

**Formatos de vídeo:** quiz, "Complete o versículo", "Verdadeiro ou falso" e **"Em qual livro está?"** (versículo + 4 livros; use `book` nos horários em `config/settings.json` ou no painel).

Se a IA falhar ou o limite grátis acabar, o sistema usa o banco **automaticamente**. O post do dia nunca deixa de sair.

### Medir → ajustar (sozinho)

- **Alerta de automação parada / token vencendo** (`app/health.py`, de hora em hora): se nada for publicado há 12h, se um post aprovado atrasar mais de 2h, se os posts do dia não forem gerados até as 08:00 ou se o token da Meta, do YouTube ou do TikTok estiver vencido ou para vencer em até 7 dias, abre uma **issue no GitHub** (chega no seu e-mail). Ela fecha sozinha quando tudo volta ao normal. Limites em `alerts` no `config/settings.json`.
- **Teste A/B de ganchos**: cada post registra qual frase abriu a legenda (`hook`; legenda escrita pela IA conta como "Legenda da IA"). O resumo semanal compara o tempo assistido médio de cada gancho por formato (só conclui com 10+ posts por gancho).
- **Resumo semanal com recomendação** (segunda-feira): além dos números, diz "corte X, aumente Y", qual gancho aposentar e qual horário mudar. O indicador principal é o **tempo assistido** (visualizações × tempo médio assistido, somando Facebook, Instagram e YouTube), não curtidas.
- **Grade adaptativa** (`app/adapt.py`): se um formato passa 2 semanas com alcance zero, 1 horário dele vai para o formato que mais alcança. O total de posts não muda, o Versículo continua no primeiro horário e há no máximo 1 ajuste a cada 14 dias. Desligue com `"adapt": {"enabled": false}`.
- **Carrossel de versículo no Instagram**: o Versículo do dia sai como carrossel 4:5 de 4 slides (versículo → reflexão → aplicação prática → chamada para salvar, enviar e seguir). A aplicação é escrita pela IA (validada) ou vem de frases prontas, e dá para editar no painel. Desligue com `publishing.verse_carousel: false`.

**Legendas pensadas para busca** (`app/keywords.py`): o tema do versículo (campo `theme` do banco) vira a palavra-chave que as pessoas buscam ("Versículo para ansiedade", "Versículo de esperança", "Versículo para a família"…). Ela entra na **primeira linha da legenda** (Instagram, Facebook, TikTok, Kwai e descrição do YouTube), no **começo do título do YouTube**, nas **hashtags** (`#versiculoparaansiedade #ansiedade`) e nas tags do vídeo. Vale para o Versículo do dia e o "Complete o versículo" (nunca com a palavra escondida). Tema sem frase de busca na lista fica sem a linha.

**Repost do melhor post da semana** (`app/repost.py`): todo **domingo às 19:15** o post com mais engajamento dos últimos 7 dias volta **em outro formato** (quiz → verdadeiro ou falso, verdadeiro ou falso → quiz, versículo → complete o versículo, complete o versículo → versículo). O mesmo post nunca volta duas vezes, e o repost fica fora das comparações de formato, gancho e horário do resumo semanal. Ajuste ou desligue em `"repost": {"enabled": true, "weekday": 6, "time": "19:15", "days": 7}`.

**Capas e títulos para o YouTube**: cada Short ganha uma capa 9:16 com texto grande ("SÓ 1% ACERTA" + a pergunta, sem a resposta) e um título curto com a palavra-chave na frente ("Quiz Bíblico: …"), além de tags. O vídeo longo ganha miniatura 16:9 no mesmo estilo → [docs/PUBLICACAO.md](docs/PUBLICACAO.md#capas-e-títulos-do-youtube).

**Mini-site público** em `/hoje/`: versículo do dia + quiz de hoje (com placar), uma página por dia para o Google e o link para pôr na bio → [docs/SITE.md](docs/SITE.md).

**Toda semana** (sábado, 12:00) também monta um **vídeo longo de ~10 min com ~40 perguntas de quiz** para o YouTube → [docs/PUBLICACAO.md](docs/PUBLICACAO.md#vídeo-longo-de-quiz-no-youtube-10-minutos).

## Exemplos

| Versículo do dia | Desafio de quiz |
|---|---|
| **Imagem** 9:16, 4:5 e 1:1: versículo + referência + seu @ (reflexão vai na legenda). Para voltar a ter vídeo: `video.video_types` = `["quiz", "verse"]` em `config/settings.json` | "SÓ 1% ACERTA" + pergunta + 4 alternativas já no primeiro quadro → "Comente a letra" → contagem 3…1 → resposta revelada → volta à pergunta (vídeo de 8 a 12 s em loop, sem tela final) |

---

## Arquitetura (e por que cada peça)

```
                ┌──────────────────────────────┐
  todo dia ───▶ │ GitHub Actions (grátis)      │
  05:20         │  Python + FFmpeg             │
                │  1. escolhe conteúdo         │◀── content/bank/*.json (banco)
                │  2. valida na Bíblia local   │◀── data/bible (domínio público)
                │  3. legendas (+ Groq, opc.)  │◀── Groq API (grátis)
                │  4. vídeo/imagens + música   │◀── assets/music (faixas próprias)
                └──────┬────────────┬──────────┘
                       │            │
        state/*.json   │            │  vídeos e imagens
        (fila, histórico)           │  (branch "media", imagens de 30 dias)
                       ▼            ▼
                ┌──────────────────────────────┐
                │ Cloudflare Pages (grátis)    │  https://SEU-PROJETO.pages.dev
                │  painel + mídias + login     │◀── você, no celular
                │  Functions: aprovar/editar   │──▶ grava no GitHub / pede re-render
                └──────────────────────────────┘
```

| Peça | Por quê |
|---|---|
| **GitHub Actions** | Agenda diária e "computador" para montar vídeos com FFmpeg, de graça. |
| **Python + Pillow + FFmpeg** | Desenho das artes e montagem de vídeo, tudo livre e sem serviço pago. |
| **Arquivos JSON no repositório** | Banco de dados simples, gratuito, com histórico de tudo e fácil de editar. |
| **Branch `media` sem histórico** | Guarda as imagens dos últimos 30 dias (`media_retention_days`), para o Histórico e as páginas do mini-site; os vídeos saem assim que o post deixa a fila, para o repositório não inchar. |
| **Cloudflare Pages + Functions** | Hospeda o painel e as mídias de graça, com uso comercial permitido (ao contrário do plano grátis da Vercel). |
| **Login com senha própria** | Só você entra. Funciona sem cartão. O Cloudflare Access é uma camada extra opcional. |
| **Groq (opcional)** | IA grátis para variar legendas e criar conteúdo novo, sempre validado. |

## Bíblia usada: Bíblia Portuguesa Mundial (domínio público)

NVI, ARA, NTLH e ARC têm direitos autorais. Este projeto usa a **Bíblia
Portuguesa Mundial (BPM)**, em **domínio público** (fonte:
[eBible.org](https://ebible.org/Scriptures/details.php?id=porbrbsl)), em português
brasileiro atual. Mesmo sem ser obrigatório, as legendas dão o crédito:
*"Texto bíblico: Bíblia Portuguesa Mundial (domínio público)"*.

⚠️ A BPM ainda é um **rascunho em revisão**. Encontrei e removi restos de
tradução automática em 7 versículos (ex.: Nm 13:33, Lc 7:50, Sl 88:18). Também
existe uma **trava** que impede publicar qualquer versículo com texto suspeito.
Detalhes em [docs/CONTEUDO.md](docs/CONTEUDO.md).

## Custos (plano grátis de cada serviço)

| Serviço | Limite grátis | Uso estimado |
|---|---|---|
| GitHub (repo privado) | 2.000 min/mês de Actions | ~120–200 min/mês |
| Cloudflare Pages | sites estáticos ilimitados, 100 mil req/dia nas Functions, 20 mil arquivos, 25 MB por arquivo | poucas centenas de req/dia |
| Groq | limites diários por modelo (veja no console) | ≤ 6 chamadas/dia (configurável) |
| Endereço `.pages.dev` | grátis | — |
| Bíblia, fontes, músicas | domínio público / OFL / composições próprias | — |

**Total: R$ 0,00 por mês.**

---

## Como colocar no ar

Siga **[docs/PASSO-A-PASSO.md](docs/PASSO-A-PASSO.md)**. São cerca de 30 minutos,
uma vez só: criar as contas grátis, colar as chaves e rodar a primeira geração.

## Uso diário (5 minutos)

0. O painel abre na aba **Hoje**: problemas encontrados pela verificação (`app/health.py`), os posts do dia em linha do tempo (✅ publicado, ⏳ aguardando, ❌ erro, ⏭ pulado; toque para abrir o card), envios ao YouTube, chamadas da Groq e dias de banco por formato. A aba **Agenda** mostra os próximos 7 dias (datas especiais, vídeo longo, repost). Enquanto o GitHub Actions roda, o painel se atualiza sozinho.
   - **⏸ Pausar publicações** (no topo): para dias de luto, tragédia ou viagem. Nada é publicado até retomar; ao retomar, os posts que perderam o horário são pulados (ou publicados, se você escolher).
   - Gerar fora do horário: **Configurações → Gerar só o que falta** (não apaga nada) ou **Refazer o dia do zero** (apaga a fila; pede para digitar REFAZER).
1. Abra o painel no celular → aba **Fila**.
2. Veja o vídeo, toque em **Aprovar** (ou **Editar**).
3. **Baixe**:
   - *vídeo sem música* → TikTok, Kwai e Reels (escolha uma das **músicas gospel sugeridas** no app);
   - *vídeo com música* → YouTube Shorts e Facebook;
   - *imagens* → feed do Instagram/Facebook (no quiz, poste **pergunta + resposta** em carrossel).
4. Toque em **Copiar legenda** na aba da rede e cole no app.
5. Marque **Onde já publiquei**. Fica no **Histórico**.

## Estrutura do projeto

```
app/                  código Python
  bible.py            Bíblia local + validação de referências
  validate.py         regras de validação (banco e IA)
  content.py          escolha do conteúdo (banco + Groq, sem repetir)
  captions.py         legendas e hashtags por rede
  music.py            biblioteca de músicas e sugestões gospel
  render/             artes e vídeos (verse.py, quiz.py, design.py, video.py, cover.py = capas do YouTube)
  generate.py         comando principal (gerar / re-renderizar / aplicar / vídeo longo)
  compilation.py      vídeo longo de quiz (16:9, ~10 min) para o YouTube
  youtube_seo.py      títulos e tags do YouTube
  site.py             mini-site público (/hoje/ e /dia/AAAA-MM-DD/)
  publishers/         (fases 2–4) postagem automática
content/bank/         banco: verses.json, quizzes.json, curiosities.json
content/              hashtags.json, gospel_suggestions.json
config/settings.json  configurações (também editáveis pelo painel)
state/                fila, histórico e controle de repetição (gravados pelo sistema)
assets/               fontes (OFL) e músicas
dashboard/            painel (public/ = telas, functions/ = API, lib/ = login e GitHub)
data/bible/           Bíblia Portuguesa Mundial (domínio público)
docs/                 guias
```

## Comandos úteis (no seu computador, opcional)

```bash
pip install -r requirements.txt          # precisa também do ffmpeg instalado
python -m app.validate                   # confere o banco inteiro contra a Bíblia
python -m app.saturation                 # quantos dias de conteúdo inédito restam por formato
python -m app.report --analysis          # quais formatos rendem, quais cortar (--apply grava a agenda)
python -m app.adapt                      # o que a grade adaptativa mudaria (--apply grava)
python -m app.health                     # checagem de saúde: publicação parada e tokens
python -m unittest -v                    # testes
python -m app.generate run --no-groq     # gera os posts de hoje em ./media
python -m app.generate compilation       # gera o vídeo longo de quiz (leva ~10 min)
python -m app.site --out /tmp/site       # gera o mini-site público (versículo + quiz de hoje)
python scripts/make_music.py             # recria as faixas instrumentais
python -m app.report --analysis           # desempenho de todo o histórico (por tipo e horário)
python scripts/audit_bible.py            # procura restos de tradução automática na Bíblia local
```

## Próximos passos

- Fase 2: YouTube Shorts automático · Fase 3: Instagram/Facebook · Fase 4: TikTok → [docs/FASES.md](docs/FASES.md)
- Tipo "Você sabia?" (o banco já está pronto e validado) e reflexões em vídeo
- Ampliar o banco para 365 dias
- Monetização por fases (metas, opções e regras): [docs/MONETIZACAO.md](docs/MONETIZACAO.md)
- Futuro: Telegram, ofertas de afiliados (com aviso "link de afiliado") e divulgação do jogo de quiz (veja `app/types.py`)
