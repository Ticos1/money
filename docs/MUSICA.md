# Música nos vídeos

Cada post gera **duas versões** do vídeo:

| Versão | Para quê | Música |
|---|---|---|
| `video_com_musica.mp4` | YouTube Shorts, Facebook, postagens automáticas | instrumental livre de direitos, em **volume baixo** (16%, ajustável em `config/settings.json → video.music_volume`) |
| `video_sem_musica.mp4` | TikTok, Kwai, Instagram (manual) | nenhuma: você escolhe uma música gospel **da biblioteca do próprio app** |

Por que nunca embutimos músicas de artistas gospel no arquivo? Elas têm
direitos autorais. O sistema de identificação de conteúdo (Content ID) bloqueia
ou tira o áudio, e a conta pode levar avisos. Já a biblioteca de sons do
TikTok, Kwai e Instagram é **licenciada pela própria plataforma** para uso
dentro dela.

## A biblioteca de instrumentais (`assets/music/library.json`)

O sistema escolhe a faixa pelo **clima** do post e faz rodízio para não repetir:
- `reflexao`: versículos mais contemplativos
- `alegria`: versículos de celebração e esperança
- `desafio`: quiz (pulso leve, clima de contagem)

### Faixas que já vêm prontas (composições próprias)

As 6 faixas em `assets/music/generated/` foram **compostas por código**
(`scripts/make_music.py`): pad, piano e violão dedilhado no estilo worship. Por
serem geradas aqui, **são suas**: não há risco de Content ID nem licença de
terceiros. Ouça-as. Se não gostar de alguma, desative com `"enabled": false` ou
troque por faixas do Pixabay.

### Como adicionar faixas do Pixabay Music

1. Acesse <https://pixabay.com/music/>, filtre por *piano*, *ambient*, *worship* ou *acoustic*.
2. Abra a faixa e confira a licença (**Pixabay Content License**: uso comercial
   permitido e atribuição não obrigatória).
   - Alguns autores registram as faixas no Content ID. Se a página da faixa
     avisar isso, **pule-a**.
3. Baixe o MP3 e coloque em `assets/music/pixabay/`.
4. Adicione em `assets/music/library.json`:

```json
{"id": "pixabay-calm-piano", "title": "Calm Piano", "mood": "reflexao",
 "file": "pixabay/calm-piano.mp3",
 "source": "Pixabay Music — autor: NOME DO AUTOR",
 "license": "Pixabay Content License (uso comercial permitido)",
 "url": "https://pixabay.com/music/...link-da-faixa...", "enabled": true}
```

5. Faça o commit. Na próxima geração ela entra no rodízio.

**Guarde a prova:** salve a página da faixa em PDF (com data) numa pasta sua.

### Biblioteca de Áudio do YouTube

As faixas do YouTube Studio → **Biblioteca de áudio** marcadas como *"Atribuição
não obrigatória"* podem ser usadas em vídeos do YouTube. Os termos foram feitos
para o YouTube, e a versão "com música" também vai para o Facebook. Por isso,
prefira as composições próprias ou o Pixabay. Se usar uma faixa do YouTube,
registre `source` e `license` do mesmo jeito.

## Sugestões de músicas gospel (no painel)

Cada post mostra **3 sugestões** de músicas gospel que combinam com o tema, para
você buscar na biblioteca de sons do app na hora de postar o vídeo sem música.

- A lista fica em `content/gospel_suggestions.json` (tema e clima de cada música).
- O sistema **não consegue saber automaticamente** o que está em alta no TikTok
  ou no Reels: as plataformas não oferecem isso de graça por API. Atualize a
  lista de vez em quando com as músicas que você vê em alta. Basta editar o
  arquivo.
- **Atenção:** contas **Empresa** no TikTok e no Instagram só acessam a
  biblioteca *comercial* (sem as músicas populares). Use conta **pessoal ou de
  Criador** para ter acesso às músicas gospel do momento.
