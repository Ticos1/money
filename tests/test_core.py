"""Testes rápidos (sem rede e sem FFmpeg). Rode com: python -m unittest -v"""
import json
import random
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app import bible, captions, content, state, validate
from app.groq_client import GroqClient

SETTINGS = {
    "brand": {"handle": "@teste"},
    "groq": {"enabled": True, "model": "m1", "fallback_models": [], "max_calls_per_day": 5,
             "new_content_ratio": 1.0, "caption_variations": True},
}
TODAY = date(2026, 10, 9)


class FakeGroq(GroqClient):
    """Groq de mentira: devolve respostas prontas, na ordem."""

    def __init__(self, responses):
        super().__init__("chave-falsa", SETTINGS, {}, TODAY)
        self.responses = list(responses)

    def chat_json(self, system, user, temperature=0.8):
        self.calls += 1
        self.last_model = "m1"
        if not self.responses:
            from app.groq_client import GroqUnavailable
            raise GroqUnavailable("sem respostas")
        return self.responses.pop(0)


class BibleTests(unittest.TestCase):
    def test_jo_vs_joao(self):
        self.assertEqual(bible.parse_reference("Jó 19:25").book, "JOB")
        self.assertEqual(bible.parse_reference("João 3:16").book, "JOH")
        self.assertEqual(bible.parse_reference("Jo 3:16").book, "JOH")
        self.assertEqual(bible.parse_reference("1 Co 13:4").label, "1 Coríntios 13:4")

    def test_invalid_references(self):
        for ref in ("João 3:99", "Salmos 151:1", "Livro 1:1", "Gênesis", "João 3:16-40"):
            with self.assertRaises(bible.BibleError, msg=ref):
                bible.parse_reference(ref)

    def test_artifacts_removed(self):
        text = bible.get_text(bible.parse_reference("Lucas 7:50"))
        self.assertNotIn("tradução", text)
        self.assertTrue(text.endswith("Vá em paz.”"))

    def test_numbers(self):
        passage = bible.get_text(bible.parse_reference("Gênesis 5:27"))
        self.assertTrue(bible.answer_supported(passage, "969"))
        self.assertFalse(bible.answer_supported(passage, "930"))


class ValidationTests(unittest.TestCase):
    def test_bank_is_valid(self):
        for kind in validate.VALIDATORS:
            for item in validate.load_bank(kind):
                validate.validate(kind, item)

    def test_bank_has_90_days(self):
        self.assertGreaterEqual(len(validate.load_bank("verse")), 90)
        self.assertGreaterEqual(len(validate.load_bank("quiz")), 90)
        self.assertGreaterEqual(len(validate.load_bank("curiosity")), 90)

    def test_quiz_wrong_answer_rejected(self):
        bad = {"question": "Quantos dias choveu?", "options": ["7", "40", "100", "150"], "answer": 0,
               "ref": "Gênesis 7:12", "evidence": "quarenta dias"}
        with self.assertRaises(validate.ContentError):
            validate.validate_quiz(bad)


class ContentTests(unittest.TestCase):
    def test_groq_quiz_accepted_when_valid(self):
        groq = FakeGroq([{"question": "Em que rio Jesus foi batizado por João?",
                          "options": ["Jordão", "Nilo", "Tigre", "Eufrates"], "answer": 0,
                          "ref": "Mateus 3:13", "difficulty": "facil"}])
        item, _ = content.pick("quiz", TODAY, {}, groq, SETTINGS, random.Random(1), [])
        self.assertEqual(item["source"], "groq")

    def test_groq_quiz_with_wrong_reference_falls_back_to_bank(self):
        groq = FakeGroq([
            {"question": "Quem matou Golias?", "options": ["Davi", "Saul", "Jônatas", "Samuel"],
             "answer": 0, "ref": "Gênesis 1:1"},          # resposta não está no versículo
            {"question": "X?", "options": ["a", "b", "c", "d"], "answer": 0, "ref": "Livro 99:1"},
        ])
        log = []
        item, _ = content.pick("quiz", TODAY, {}, groq, SETTINGS, random.Random(1), log)
        self.assertEqual(item["source"], "bank")
        self.assertEqual(len([l for l in log if "descartada" in l]), 2)

    def test_groq_down_uses_bank(self):
        groq = FakeGroq([])
        item, updates = content.pick("verse", TODAY, {}, groq, SETTINGS, random.Random(2), [])
        self.assertEqual(item["source"], "bank")
        self.assertIn(item["id"], updates["verse"])

    def test_no_repetition(self):
        used = {"verse": {}, "refs": {}}
        no_groq = GroqClient(None, SETTINGS, {}, TODAY)
        seen = set()
        for i in range(30):
            item, upd = content.pick("verse", TODAY, used, no_groq, SETTINGS, random.Random(i), [])
            self.assertNotIn(item["id"], seen)
            seen.add(item["id"])
            for k, v in upd.items():
                used.setdefault(k, {}).update(v)


class CaptionTests(unittest.TestCase):
    def _quiz(self):
        return validate.validate("quiz", validate.load_bank("quiz")[0])

    def test_groq_caption_revealing_answer_is_rejected(self):
        item = self._quiz()
        answer = item["options"][item["answer"]]
        groq = FakeGroq([{"hook": "Desafio!", "long": f"A resposta é {answer} dias", "short": "Responda!",
                          "youtube_title": "Quiz"}])
        log = []
        caps, source = captions.build("quiz", item, SETTINGS, groq, random.Random(1), log)
        self.assertEqual(source, "template")
        self.assertNotIn(f"A resposta é {answer}", caps["instagram"])

    def test_template_caption_has_hashtags_and_attribution(self):
        item = validate.validate("verse", validate.load_bank("verse")[0])
        caps, _ = captions.build("verse", item, {**SETTINGS, "groq": {"enabled": False}},
                                 GroqClient(None, SETTINGS, {}, TODAY), random.Random(1), [])
        self.assertIn("#", caps["instagram"])
        self.assertIn("Bíblia Portuguesa Mundial", caps["instagram"])
        self.assertLessEqual(len(caps["youtube"]["title"]), 100)
        self.assertLessEqual(caps["tiktok"].count("#"), 5)


class StateTests(unittest.TestCase):
    def test_apply_patch_is_idempotent_and_keeps_user_actions(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)):
            post = {"id": "2026-10-09-1-verse", "date": "2026-10-09", "slot": 1, "status": "pending",
                    "captions": {"x": 1}, "published": {p: None for p in state.PLATFORMS}}
            patch = {"posts": [post], "used": {"verse": {"v001": "2026-10-09"}},
                     "groq_usage": {"date": "2026-10-09", "calls": 2}}
            state.apply_patch(patch, TODAY, 30)
            state.apply_patch(patch, TODAY, 30)
            self.assertEqual(len(state.load_queue()), 1)
            # usuário marcou como publicado no TikTok pelo painel
            q = state.load_queue()
            q[0]["published"]["tiktok"] = "2026-10-09T10:00:00Z"
            q[0]["status"] = "approved"
            state.save_queue(q)
            rer = {"mode": "rerender", "posts": [{**post, "media": {"version": 2}}]}
            state.apply_patch(rer, TODAY, 30)
            after = state.load_queue()[0]
            self.assertEqual(after["published"]["tiktok"], "2026-10-09T10:00:00Z")
            self.assertEqual(after["status"], "approved")
            self.assertEqual(after["media"]["version"], 2)

    def test_old_posts_are_archived(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)):
            old = {"id": "2026-08-01-1-quiz", "date": "2026-08-01", "slot": 1, "media": {"a": 1}}
            state.apply_patch({"posts": [old]}, TODAY, 30)
            self.assertEqual(state.load_queue(), [])
            hist = state.load_history()
            self.assertEqual(hist[0]["id"], old["id"])
            self.assertNotIn("media", hist[0])


if __name__ == "__main__":
    unittest.main()
