# Plano de monetização (passo a passo, sem pular etapas)

Hoje o projeto **não tem nenhum caminho de receita**: o alcance ainda é mínimo
(veja `python -m app.report --analysis`). Monetizar antes de ter público só gera
frustração. Por isso o plano é em **fases com metas**: só avance quando a meta da
fase anterior for batida.

> As regras dos programas de monetização (YouTube, Meta) mudam com frequência.
> Os números abaixo são o que valia quando este guia foi escrito: **confirme a
> regra atual no YouTube Studio e no Meta Business Suite** antes de planejar em cima delas.

## Fase 0: provar que o conteúdo funciona (semanas 1 a 4)

Meta: **qualquer formato com alcance médio ≥ 100 pessoas por post** no Instagram.

1. Rode `python -m app.report --analysis` toda semana e veja qual tipo e qual horário rendem mais.
2. Faça mais do que funciona e menos do que não funciona (ajuste os horários em `config/settings.json`
   ou na aba Configurações do painel). Se nada passar de 100 de alcance, o problema é o **gancho**
   dos 2 primeiros segundos, não a monetização.
3. Teste a versão **sem música** com música em alta no app (3 a 5 vídeos por semana).
4. **Responda todos os comentários** nas primeiras horas: é o que mais ajuda o alcance de uma conta nova.

## Fase 1: transformar seguidor em contato direto (semanas 4 a 12)

Meta: **500 seguidores** e **100 pessoas** num canal seu.

Redes sociais podem mudar o algoritmo ou bloquear a conta; uma lista de contato é seu ativo.
- Crie um **canal do WhatsApp** (ou grupo no Telegram) com o versículo do dia.
- Chame para ele no fim dos vídeos e na bio (uma única chamada para ação, não várias).
- Opcional: lista de e-mail com um brinde simples (PDF "7 dias de versículos").

## Fase 2: primeira receita (a partir de 500 seguidores engajados)

Escolha **uma** opção, não todas ao mesmo tempo.

| Opção | Esforço | Receita esperada | Observação |
|---|---|---|---|
| **Doações voluntárias** (PIX, Apoia.se, Catarse) | Baixo | Pequena, mas real | Combina bem com conteúdo cristão. Peça com humildade, sem pressão. |
| **Produto digital próprio** (PDF/devocional de 30 dias, cartões de versículos, quiz bíblico em PDF) | Médio | Média | O sistema já gera imagens e o banco de conteúdo valida tudo na Bíblia: dá para montar um PDF rápido. Venda por Hotmart, Eduzz, Kiwify ou Mercado Pago. |
| **Afiliados** (Bíblias, devocionais, livros cristãos) | Baixo | Pequena a média | **Obrigatório avisar** que é link de afiliado, na legenda e no vídeo (regra das plataformas e do CONAR). Só indique o que você conhece. |
| **Divulgar o jogo de quiz** | Médio | Depende do jogo | O README já prevê. É a ponte natural: o público já responde quiz todo dia. |

## Fase 3: programas das plataformas (quando o público existir)

- **YouTube Parceiro:** exige um mínimo de inscritos e de horas de exibição ou de visualizações de Shorts.
  Veja os números atuais em YouTube Studio → Ganhar dinheiro. O vídeo longo semanal de quiz (10 min) ajuda
  nas horas de exibição.
- **Meta (Facebook/Instagram):** os programas de bonificação costumam ser por convite e variam por país.
  Veja em Meta Business Suite → Monetização. Não dependa deles.

## Regras que valem em qualquer fase

- **Sem teologia da prosperidade** e sem prometer cura ou riqueza em troca de compra ou doação.
- **Transparência:** link de afiliado sempre identificado; nunca esconda patrocínio.
- **Direitos autorais:** o projeto usa só Bíblia de domínio público, fontes OFL e música própria. Mantenha assim
  em qualquer produto que vender (não coloque NVI/ARA/NTLH num PDF à venda sem licença).
- **Imposto:** ao receber valores com regularidade, formalize (por exemplo, MEI) e consulte um contador.
- **Não compre seguidores nem use robôs de interação**: derruba o alcance e pode banir a conta.

## Como acompanhar

| O que olhar | Onde | Meta de referência |
|---|---|---|
| Alcance médio por post | `python -m app.report --analysis` | ≥ 100 (fase 0) |
| Melhor formato e horário | mesmo comando | refazer a grade a cada 2 semanas |
| Seguidores / inscritos | App de cada rede | 500 antes da fase 2 |
| Pessoas no WhatsApp/Telegram | O próprio app | 100 antes da fase 2 |

Revise este plano a cada mês e anote o que mudou.
