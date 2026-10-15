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

---

## O que o sistema faz todo dia

1. Às **05:17 (Brasília)**, o GitHub Actions acorda e gera os posts do dia (padrão: **9 posts** — 1 Versículo do dia e 8 vídeos: 4 quizzes, 2 "Complete o versículo" e 2 "Verdadeiro ou falso"; até 12, configurável no painel). O "Você sabia?" saiu da agenda porque não rendeu (veja `python -m app.report --analysis`).
2. Escolhe o conteúdo:
   - **banco próprio** (457 versículos com reflexão, 948 perguntas de quiz e 267 curiosidades, ou seja, vários meses);
   - às vezes pede **conteúdo novo à IA (Groq, grátis)**.
3. **Confere toda referência bíblica** contra a Bíblia salva no projeto. Se o livro, capítulo ou versículo não existir, ou se a resposta do quiz não estiver no texto, **descarta**.
4. Monta o **vídeo** com texto animado em **duas versões**:
   - **com música** instrumental livre de direitos (para YouTube e Facebook);
   - **sem música** (para você escolher uma música gospel no próprio TikTok, Kwai ou Instagram).
5. Gera as **imagens** quadrada (1080×1080) e vertical (1080×1350), com a sua marca d'água.
6. Escreve **legendas e hashtags diferentes para cada rede**.
7. Coloca tudo no **painel** (fila), aguardando sua aprovação.

Se a IA falhar ou o limite grátis acabar, o sistema usa o banco **automaticamente**. O post do dia nunca deixa de sair.

### Medir → ajustar (sozinho)

- **Alerta de automação parada / token vencendo** (`app/health.py`, de hora em hora): se nada for publicado há 12h, se um post aprovado atrasar mais de 2h, se os posts do dia não forem gerados até as 08:00 ou se o token da Meta, do YouTube ou do TikTok estiver vencido ou para vencer em até 7 dias, abre uma **issue no GitHub** (chega no seu e-mail). Ela fecha sozinha quando tudo volta ao normal. Limites em `alerts` no `config/settings.json`.
- **Teste A/B de ganchos**: cada post registra qual frase abriu a legenda (`hook`; legenda escrita pela IA conta como "Legenda da IA"). O resumo semanal compara o alcance médio de cada gancho por formato.
- **Resumo semanal com recomendação** (segunda-feira): além dos números, diz "corte X, aumente Y", qual gancho aposentar e qual horário mudar.
- **Grade adaptativa** (`app/adapt.py`): se um formato passa 2 semanas com alcance zero, 1 horário dele vai para o formato que mais alcança. O total de posts não muda, o Versículo continua no primeiro horário e há no máximo 1 ajuste a cada 14 dias. Desligue com `"adapt": {"enabled": false}`.
- **Carrossel de versículo no Instagram**: o Versículo do dia sai como carrossel 4:5 de 4 slides (versículo → reflexão → aplicação prática → chamada para salvar, enviar e seguir). A aplicação é escrita pela IA (validada) ou vem de frases prontas, e dá para editar no painel. Desligue com `publishing.verse_carousel: false`.

**Toda semana** (sábado, 12:00) também monta um **vídeo longo de ~10 min com ~40 perguntas de quiz** para o YouTube → [docs/PUBLICACAO.md](docs/PUBLICACAO.md#vídeo-longo-de-quiz-no-youtube-10-minutos).

## Exemplos

| Versículo do dia | Desafio de quiz |
|---|---|
| **Imagem** 9:16, 4:5 e 1:1: versículo + referência + seu @ (reflexão vai na legenda). Para voltar a ter vídeo: `video.video_types` = `["quiz", "verse"]` em `config/settings.json` | "SÓ 1% ACERTA" → pergunta → 4 alternativas → contagem 5…1 → resposta revelada → "Você acertou?" |

---

## Arquitetura (e por que cada peça)

```
                ┌──────────────────────────────┐
  todo dia ───▶ │ GitHub Actions (grátis)      │
  05:17         │  Python + FFmpeg             │
                │  1. escolhe conteúdo         │◀── content/bank/*.json (banco)
                │  2. valida na Bíblia local   │◀── data/bible (domínio público)
                │  3. legendas (+ Groq, opc.)  │◀── Groq API (grátis)
                │  4. vídeo/imagens + música   │◀── assets/music (faixas próprias)
                └──────┬────────────┬──────────┘
                       │            │
        state/*.json   │            │  vídeos e imagens
        (fila, histórico)           │  (branch "media", só últimos 30 dias)
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
| **Branch `media` sem histórico** | Guarda só os últimos 30 dias de vídeos, para o repositório não inchar. |
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
  render/             artes e vídeos (verse.py, quiz.py, design.py, video.py)
  generate.py         comando principal (gerar / re-renderizar / aplicar / vídeo longo)
  compilation.py      vídeo longo de quiz (16:9, ~10 min) para o YouTube
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
python scripts/make_music.py             # recria as faixas instrumentais
```

## Próximos passos

- Fase 2: YouTube Shorts automático · Fase 3: Instagram/Facebook · Fase 4: TikTok → [docs/FASES.md](docs/FASES.md)
- Tipo "Você sabia?" (o banco já está pronto e validado) e reflexões em vídeo
- Ampliar o banco para 365 dias
- Futuro: Telegram/WhatsApp, ofertas de afiliados (com aviso "link de afiliado") e divulgação do jogo de quiz (veja `app/types.py`)
