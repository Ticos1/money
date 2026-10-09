# Conteúdo: banco, IA e validação bíblica

## A tradução bíblica

| Tradução | Situação | Uso aqui |
|---|---|---|
| NVI, ARA, NTLH, NAA, ARC (edições modernas), ACF | Direitos autorais (Sociedade Bíblica / editoras) | ❌ não usar sem licença |
| **Bíblia Portuguesa Mundial (BPM)** | **Domínio público** ([eBible.org](https://ebible.org/Scriptures/details.php?id=porbrbsl)) | ✅ **usada** |
| Bíblia Livre (BLIVRE) | CC BY 4.0 (uso comercial com crédito obrigatório) | alternativa possível |

A BPM é uma tradução em português brasileiro atual, completa (66 livros, mais os
deuterocanônicos, que o sistema **ignora**). Fica em `data/bible/bpm.json.gz`,
gerado por `scripts/build_bible.py` a partir do arquivo oficial do eBible.org.

### Cuidados com a BPM (ela ainda está em revisão)
- **Restos de tradução automática** foram encontrados e removidos em 7
  versículos: Nm 13:33, Jr 1:19, Lm 2:22, Lc 7:50 (frases "Aqui está a
  tradução…") e Sl 88:18, Sl 98:9, Is 42:25 (marcas "```usfm").
- Há uma **trava permanente**: qualquer versículo com esse tipo de texto é
  recusado e nunca é publicado.
- Os títulos de Salmos fazem parte do versículo 1 (ex.: *"Um Salmo de Davi. O
  SENHOR é o meu pastor…"*). No banco, `skip_prefix` remove o título na exibição,
  e o sistema confere que o título removido é exatamente o do texto.
- Se um dia quiser atualizar a BPM: baixe `porbrbsl_vpl.zip` no eBible.org e rode
  `python scripts/build_bible.py porbrbsl_vpl.txt`. Depois rode `python -m app.validate`.

## O banco (`content/bank/`)

| Arquivo | Itens | Campos principais |
|---|---|---|
| `verses.json` | 95 | `ref`, `on_screen` (frase do vídeo, até 110 caracteres), `reflection` (legenda), `mood`, `tags` |
| `quizzes.json` | 95 | `question`, `options` (4), `answer` (0 a 3), `ref`, `evidence` (trecho literal do versículo) |
| `curiosities.json` | 102 | `title`, `text`, `ref`, `evidence` |

O sistema **não repete**: `state/used.json` guarda o que já saiu, e o mesmo
versículo não volta antes de 180 dias. Quando o banco acaba, ele recorre à
Groq. Se a Groq também falhar, reaproveita o item usado há mais tempo.

### Regras de validação (valem para o banco **e** para a IA)
1. A referência precisa existir (livro, capítulo e versículo) na BPM.
2. Quiz e curiosidade: a `evidence` precisa estar **literalmente** no texto
   (sem considerar acentos; números podem estar por extenso).
3. Quiz: a alternativa correta precisa aparecer no texto, e **nenhuma alternativa
   errada** pode aparecer também, para não haver pergunta com duas respostas.
4. Tamanhos máximos para caber no vídeo.

Para conferir tudo: `python -m app.validate`. Isso também roda em cada push, no
workflow "Testes".

### Como adicionar itens (ex.: chegar a 365 dias)
Edite os JSON seguindo o formato dos itens existentes (IDs únicos), rode
`python -m app.validate` e faça o commit. Também posso gerar mais lotes aqui no
chat, já validados.

## A IA (Groq), como complemento
- **Conteúdo novo:** em cerca de 30% dos dias (`groq.new_content_ratio`), ou
  sempre que o banco acabar, a Groq propõe um versículo + reflexão ou uma
  pergunta de quiz. O **texto do versículo nunca vem da IA**: ele é sempre
  copiado da Bíblia local. A proposta passa pelas mesmas regras de validação;
  se reprovar, vale o banco.
- **Legendas:** a Groq escreve variações. Elas são recusadas se tiverem
  hashtags, citarem outros versículos ou **revelarem a resposta do quiz**.
- **Limite:** no máximo 6 chamadas por dia (configurável). Cada post usa de 1 a 3.
- A validação é forte, mas não é perfeita: ela garante que a referência existe
  e que a resposta está no texto, mas não "entende" a pergunta. Por isso a
  **aprovação no painel** vem ligada por padrão. Quando você confiar no
  resultado, pode ativar "Aprovar automaticamente".

## Tom e cuidados editoriais
Os prompts pedem tom respeitoso, acolhedor e fiel à Bíblia, sem polêmicas
denominacionais e sem promessas de prosperidade. As reflexões do banco foram
escritas com esse cuidado. Revise e ajuste à sua voz.
