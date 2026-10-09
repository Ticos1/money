"""Registro dos tipos de post.

Fase 1 (com vídeo/imagem): "verse" e "quiz".
Prontos no banco, renderização na próxima etapa: "curiosity" ("Você sabia?").

Para adicionar um tipo novo no futuro (ex.: "reflection", "affiliate" para
ofertas com aviso de link de afiliado, "game" para divulgar o jogo de quiz):
  1. banco em content/bank/<tipo>.json + validador em app/validate.py
  2. template em app/render/<tipo>.py com a função render(...)
  3. legendas em app/captions.py
  4. registrar aqui e em app/config.VALID_TYPES
Posts de afiliado devem SEMPRE incluir o aviso "link de afiliado" na legenda
e no vídeo/imagem (regra das plataformas e do CONAR).
"""
POST_TYPES = {
    "verse": {"name": "Versículo do dia", "render": True},
    "quiz": {"name": "Desafio de quiz", "render": True},
    "curiosity": {"name": "Você sabia?", "render": False},
}
