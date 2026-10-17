# Mini-site público: versículo do dia + quiz de hoje

Junto com o painel, o sistema publica um **site aberto** (sem login) com o
versículo do dia e o quiz de hoje. Ele serve para duas coisas:

1. **Link da bio**: `https://SEU-PROJETO.pages.dev/hoje/` (ou só
   `https://SEU-PROJETO.pages.dev`, que leva quem não está logado direto para
   `/hoje/`). Coloque no Instagram, TikTok, Kwai, YouTube e WhatsApp.
2. **Tráfego do Google**: cada dia ganha uma página fixa (`/dia/2026-10-15/`)
   com o versículo, a reflexão e as perguntas. Com o tempo, são centenas de
   páginas indexáveis sobre versículos e perguntas bíblicas.

## O que tem em cada página

- **Versículo do dia**: texto exato da Bíblia local, referência e reflexão.
- **Quiz de hoje**: até 5 perguntas do dia. A pessoa toca na alternativa, vê
  se acertou e lê o versículo que traz a resposta. No fim aparece o placar
  ("Você acertou 4 de 5!").
- Botões **Compartilhar** e **Enviar no WhatsApp**, e o seu @ das redes.
- Para o Google e para a prévia do link: título e descrição próprios, imagem do
  versículo (quando ainda existe a mídia, até 30 dias), dados estruturados
  (`Quiz`), `sitemap.xml` e `robots.txt`.

Posts **rejeitados** não aparecem, nem dias futuros. Funciona em tema claro e escuro.

## Como é publicado

`python -m app.site --out dist --base-url https://SEU-PROJETO.pages.dev` roda no
workflow **Pipeline de conteúdo**, logo antes de publicar o painel. Ou seja, o
site é atualizado sozinho toda manhã, junto com os posts do dia.

O endereço vem da variável `PUBLIC_BASE_URL` (GitHub → Settings → Secrets and
variables → Actions → **Variables**). Se ela não existir, usa
`https://CF_PAGES_PROJECT.pages.dev`. Se você usar um domínio próprio, crie
`PUBLIC_BASE_URL` com ele (sem barra no final).

## O que continua protegido

O painel, a API e as mídias seguem exigindo login. O
`dashboard/functions/_middleware.js` libera só:
`/hoje/`, `/dia/...`, `/robots.txt`, `/sitemap.xml`, o arquivo de verificação do Google (`/google*.html`) e as imagens do Versículo
do dia (`/media/.../AAAA-MM-DD-N-verse/imagem_*.jpg`), usadas na prévia do link.
Vídeos e imagens dos quizzes (que mostram a resposta) continuam fechados. O
login continua em `/login`.

## Para o Google achar mais rápido (opcional, grátis)

1. Entre em [search.google.com/search-console](https://search.google.com/search-console).
2. Adicione a propriedade **Prefixo do URL** com o seu endereço.
3. Verifique pelo método **Arquivo HTML**: coloque o arquivo `googleXXXX.html` em
   `dashboard/public/` e faça o commit (esse arquivo também fica liberado sem login).
4. Em **Sitemaps**, envie `sitemap.xml`.

## Testar no computador

```bash
python -m app.site --out /tmp/site --base-url http://localhost:8000
cd /tmp/site && python -m http.server 8000   # abra http://localhost:8000/hoje/
```
