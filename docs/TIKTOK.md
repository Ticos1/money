# TikTok: Reels direto nos seus rascunhos

**Como funciona:** no horário de cada Reel (quiz), o sistema envia o vídeo
**sem música** para a caixa de entrada/rascunhos do seu TikTok. Você recebe a
notificação, abre o app, escolhe uma **música gospel em alta**, cola a legenda
(botão "Copiar legenda" → aba TikTok no painel) e publica. Leva uns 30 segundos.

Por que assim? É o caminho oficial que **não exige auditoria de interface** e
ainda deixa você usar as músicas do próprio TikTok, que dão mais alcance.
Limite do TikTok: **5 rascunhos pendentes por 24 h** (usamos 3 por dia).
Finalize os rascunhos para não acumular.

---

## 1) Conta de desenvolvedor e app (grátis)
> Use o navegador em **"Site para computador"**.

1. Acesse <https://developers.tiktok.com> → **Log in** com a sua conta do TikTok (@versoerocha).
2. Complete o cadastro de desenvolvedor, se for pedido.
3. **Manage apps → Connect an app** (ou *Create app*):
   - **App name:** `Verso e Rocha Publicador`
   - **App icon:** use o arquivo `icone-app.png` que te mandei
   - **Category:** *Lifestyle* (ou *Entertainment*)
   - **Description:** `Ferramenta pessoal para enviar meus próprios vídeos cristãos para os rascunhos do meu TikTok.`
   - **Terms of Service URL:** `https://palavra-diaria.pages.dev/termos`
   - **Privacy Policy URL:** `https://palavra-diaria.pages.dev/privacidade`
   - **Platforms:** marque **Web** → **Website URL:** `https://palavra-diaria.pages.dev/sobre`
4. Se o TikTok pedir para **verificar o site (URL properties)**:
   - escolha **URL prefix** = `https://palavra-diaria.pages.dev/` e o método **arquivo (file)**;
   - baixe o arquivo `tiktok....txt` e **me mande o nome e o conteúdo dele** (não é secreto);
   - eu coloco no ar e você toca em **Verify**.

## 2) Produtos e permissões
1. **Add products → Login Kit**
   - **Redirect URI:** `https://palavra-diaria.pages.dev/api/tiktok/callback`
2. **Add products → Content Posting API**. Não precisa ligar o "Direct Post".
3. **Scopes:** `user.info.basic` e `video.upload`.

## 3) Usar sem esperar aprovação (Sandbox)
1. Na página do app, abra a aba **Sandbox** → **Create Sandbox**.
2. Em **Target users**, adicione a **sua** conta do TikTok.
3. Copie a **Client key** e o **Client secret** do Sandbox.

O Sandbox funciona para as contas cadastradas como *target users*, que é o seu
caso. Se um dia o TikTok exigir a versão de produção, é só tocar em
**Submit for review** com o texto do "Description" acima e um vídeo
mostrando o painel.

## 4) Guardar as chaves
- **GitHub** → Settings → Secrets and variables → Actions → *New repository secret*:
  `TIKTOK_CLIENT_KEY` e `TIKTOK_CLIENT_SECRET`
- **Cloudflare** → Workers & Pages → `palavra-diaria` → Settings → Variables and Secrets (tipo *Secret*):
  `TIKTOK_CLIENT_KEY` e `TIKTOK_CLIENT_SECRET` (os mesmos valores)

## 5) Conectar e ligar
1. Peça para eu atualizar o painel (ou rode **Actions → Pipeline de conteúdo → mode `deploy`**).
2. Painel → **Configurações** → **Conectar TikTok** → autorize no TikTok.
   - Ao voltar, aparece "✅ TikTok conectado".
3. Marque **TikTok** → **Salvar configurações**.

Pronto: no horário de cada quiz chega um rascunho no seu TikTok. No painel, em
"Onde já publiquei", aparece "📥 rascunho no app do TikTok — abra o TikTok e finalize".

**Segurança:** o token do TikTok fica guardado **criptografado** no repositório
(com a chave `MEDIA_SIGNING_SECRET`) e dura cerca de 1 ano. Se expirar, é só
tocar em **Reconectar TikTok**.
