# Fases 2 a 4: postagem automática (só por APIs oficiais)

Hoje (Fase 1) você posta manualmente usando o painel. Nas próximas fases, o
sistema publica sozinho os posts **aprovados** no horário configurado e marca
"publicado" no histórico, como você já faz no painel.

Princípio: **nada de robôs, automação de navegador ou apps não oficiais**. Só
APIs oficiais, para não arriscar banimento.

| Fase | Rede | Versão do vídeo | Precisa de aprovação? |
|---|---|---|---|
| 2 | YouTube Shorts | com música | Sim: auditoria do YouTube (sem ela, os vídeos ficam **privados**) |
| 3 | Instagram (Reels + feed) e Facebook | com música | Não, se só você usar o app (modo desenvolvimento) |
| 4 | TikTok | com música | Sim: auditoria do TikTok (sem ela, os posts ficam **privados**) |
| — | Kwai | — | Sem API pública de postagem: continua manual pelo painel |

> Por que "com música" nas automáticas? Pela API não dá para escolher músicas da
> biblioteca do app. Por isso usamos nosso instrumental livre de direitos. Se
> quiser o alcance de uma música em alta no TikTok/Instagram, poste
> manualmente a versão sem música.

---

## Fase 2: YouTube Shorts (YouTube Data API v3)

### Como vai funcionar
O Actions envia o vídeo **com música** (vertical e com até 60 s, por isso vira
Short), com título e descrição da aba YouTube e `#shorts`.

### O que você vai fazer (grátis)
1. Acesse <https://console.cloud.google.com> e crie um projeto (ex.: `palavra-diaria`).
2. **APIs e serviços → Biblioteca → YouTube Data API v3 → Ativar.**
3. **Tela de consentimento OAuth:** tipo *Externo*, preencha nome e e-mail e adicione
   o escopo `.../auth/youtube.upload`.
4. **Credenciais → Criar → ID do cliente OAuth → App para computador.**
5. Rodamos um script uma vez no seu computador para você autorizar o seu canal.
   Ele gera um *refresh token* que vai para os Secrets do GitHub.
6. Coloque o app em **"Em produção"** na tela de consentimento. Em modo "Teste",
   a autorização expira a cada 7 dias.

### ⚠️ A verificação do app (importante)
Pela regra do YouTube, projetos de API criados depois de 28/07/2020 e **não
auditados** só conseguem enviar vídeos **privados**. A chamada funciona e o
vídeo sobe, mas fica privado até você mudar manualmente.

Para liberar vídeos públicos:
1. Preencha o formulário **"YouTube API Services – Audit and Quota Extension"**
   (link na documentação do `videos.insert`).
2. Descreva o uso, por exemplo: *"Ferramenta interna que publica no meu próprio
   canal vídeos curtos cristãos criados por mim; um único usuário; sem coleta de
   dados de terceiros"*.
3. Envie a política de privacidade e os termos (podemos publicar páginas
   simples no próprio `.pages.dev`) e um vídeo curto mostrando o fluxo.
4. A análise leva de algumas semanas a alguns meses.

**Enquanto não sai a aprovação:** o sistema já envia como *privado*. Você só
abre o YouTube Studio e muda para *Público*, o que já economiza tempo.

**Cota:** o padrão é 10.000 unidades/dia. O custo de cada envio já mudou mais de
uma vez; confira no Cloud Console. Para 1 a 2 Shorts por dia, sobra cota.

---

## Fase 3: Instagram e Facebook (Graph API da Meta)

### Pré-requisitos
- Instagram **profissional**. Prefira conta de **Criador** em vez de Empresa:
  contas Empresa só podem usar a "biblioteca comercial" de músicas, e as
  músicas gospel populares podem não aparecer.
- Uma **Página do Facebook** ligada a esse Instagram (Configurações do Instagram →
  Central de contas, ou pela Página).

### O que você vai fazer (grátis)
1. <https://developers.facebook.com> → **Meus apps → Criar app** (tipo *Empresa*).
2. Adicione os produtos **Instagram Graph API** e **Facebook Login para empresas**.
3. Permissões: `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
   `pages_read_engagement`, `pages_manage_posts`.
4. Gere um **token de longa duração** da Página (não expira se gerado do jeito
   certo; fazemos juntos) e salve nos Secrets do GitHub.

**Precisa de App Review?** Não, se só **você** usar o app. Em modo
desenvolvimento, as permissões funcionam para quem tem papel no app
(administrador/desenvolvedor), que é o seu caso.

### Detalhes técnicos que vamos tratar
- A Meta **baixa o vídeo por um link público**, e o seu painel é protegido por
  senha. Vamos criar links temporários assinados (válidos por 1 hora) só para a
  mídia que está sendo publicada.
- Limite oficial: **50 posts por API a cada 24 h** por conta do Instagram
  (carrossel conta como 1). Usamos 1 a 2 por dia.
- Quiz no feed vira **carrossel** (pergunta + resposta). Reels usa o vídeo vertical.

---

## Fase 4: TikTok (Content Posting API)

### O que você vai fazer (grátis)
1. <https://developers.tiktok.com> → crie a conta de desenvolvedor e um **app**.
2. Adicione **Login Kit** e **Content Posting API** (com *Direct Post*). Escopo: `video.publish`.
3. Configure o domínio/URL do app (podemos usar o `.pages.dev`).

### ⚠️ Auditoria (eu te ajudo nessa parte)
Sem auditoria, **tudo que o app posta fica privado** (`SELF_ONLY`) e há limites
de uso baixos. Para liberar posts públicos, o TikTok audita se o app segue as
regras de UX:

- mostrar o **nome/avatar da conta** que vai postar (API `creator_info`);
- deixar **você escolher a privacidade** (sem valor padrão escondido);
- mostrar **prévia** do vídeo e permitir **editar a legenda** antes;
- pedir **consentimento explícito** ("Ao postar, você concorda com a Política de
  Música do TikTok…");
- respeitar opções como desativar comentários, duetos e stitch.

O que vou preparar quando chegarmos lá:
1. Uma tela no painel, **"Postar no TikTok"**, que cumpre essas regras.
2. O **texto do pedido** de auditoria (uso: ferramenta pessoal de um criador
   publicando o próprio conteúdo cristão original).
3. O **roteiro do vídeo de demonstração** que o TikTok pede.
4. Páginas simples de **Termos de Uso** e **Política de Privacidade**.

Prazo típico informado por desenvolvedores: de algumas semanas a alguns meses.

---

## Kwai

O Kwai **não tem API pública de postagem**. Ele continua manual: baixe o vídeo
*sem música* no painel, poste pelo app (com música da biblioteca do Kwai) e
marque "publicado".
