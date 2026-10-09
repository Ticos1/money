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


class CuriosityTests(unittest.TestCase):
    def test_groq_curiosity_needs_keyword_in_verse(self):
        good = {"title": "Gigante de Gate", "text": "Golias era de Gate.", "ref": "1 Samuel 17:4",
                "keyword": "Golias", "tags": ["golias"]}
        bad = {**good, "keyword": "Sansão"}
        item, _ = content.pick("curiosity", TODAY, {}, FakeGroq([good]), SETTINGS, random.Random(1), [])
        self.assertEqual(item["source"], "groq")
        item, _ = content.pick("curiosity", TODAY, {}, FakeGroq([bad, bad]), SETTINGS, random.Random(1), [])
        self.assertEqual(item["source"], "bank")

    def test_curiosity_caption_has_text_and_reference(self):
        item = validate.validate("curiosity", validate.load_bank("curiosity")[0])
        caps, _ = captions.build("curiosity", item, {**SETTINGS, "groq": {"enabled": False}},
                                 GroqClient(None, SETTINGS, {}, TODAY), random.Random(1), [])
        self.assertIn(item["title"], caps["instagram"])
        self.assertIn(item["ref_label"], caps["instagram"])


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


class GroqRobustnessTests(unittest.TestCase):
    def test_parse_json_formats(self):
        from app.groq_client import _parse_json
        self.assertEqual(_parse_json('[{"a": 1}]'), {"a": 1})
        self.assertEqual(_parse_json('texto {"a": 2} fim'), {"a": 2})
        for bad in ('[1, 2]', '"oi"', 'sem json'):
            with self.assertRaises(ValueError):
                _parse_json(bad)

    def test_weird_groq_output_never_breaks_the_post(self):
        item = validate.validate("verse", validate.load_bank("verse")[0])
        for weird in ([], ["x"], {"hook": None, "long": 5}, {"hook": ["a"], "long": {}, "short": 1,
                                                              "youtube_title": 2}):
            groq = FakeGroq([weird])
            groq.chat_json = lambda *a, w=weird, **k: w  # devolve o formato estranho como está
            caps, source = captions.build("verse", item, SETTINGS, groq, random.Random(1), [])
            self.assertIn("instagram", caps)
        for weird in ([{"ref": None}], {"options": "abc", "answer": "x"}, {"ref": 123}):
            groq = FakeGroq([])
            groq.chat_json = lambda *a, w=weird, **k: w
            got, _ = content.pick("quiz", TODAY, {}, groq, SETTINGS, random.Random(1), [])
            self.assertEqual(got["source"], "bank")


class ReplaceRejectedTests(unittest.TestCase):
    def test_only_unpublished_rejected_posts_are_replaced(self):
        from app.generate import _replaceable
        self.assertTrue(_replaceable({"status": "rejected", "published": {"tiktok": None}}))
        self.assertFalse(_replaceable({"status": "rejected", "published": {"tiktok": "2026-10-09"}}))
        self.assertFalse(_replaceable({"status": "pending", "published": {}}))
        self.assertFalse(_replaceable({"status": "approved"}))


class PublishTests(unittest.TestCase):
    POST = {"id": "2026-10-09-2-quiz", "date": "2026-10-09", "time": "07:00", "slot": 2, "type": "quiz",
            "status": "approved", "published": {}, "captions": {},
            "media": {"base": "media/2026-10-09/2026-10-09-2-quiz/", "version": 2,
                      "video_music": "video_com_musica.mp4", "images": []}}

    def test_due_only_when_approved_and_time_passed(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.publish import is_due
        tz = ZoneInfo("America/Sao_Paulo")
        self.assertTrue(is_due(self.POST, datetime(2026, 10, 9, 7, 5, tzinfo=tz), tz))
        self.assertFalse(is_due(self.POST, datetime(2026, 10, 9, 6, 59, tzinfo=tz), tz))
        self.assertFalse(is_due({**self.POST, "status": "pending"}, datetime(2026, 10, 9, 9, 0, tzinfo=tz), tz))

    def test_publish_run_records_success_and_errors(self):
        from app import publish
        from app.publishers import PublishError

        class Ok:
            def supports(self, post): return True
            def publish(self, post, d, media_url):
                self.url = media_url("video_com_musica.mp4")
                return "https://instagram.com/p/x"

        class Bad:
            def supports(self, post): return True
            def publish(self, post, d, media_url): raise PublishError("token inválido")

        ok = Ok()
        env = {"PUBLIC_BASE_URL": "https://x.pages.dev", "MEDIA_SIGNING_SECRET": "s" * 40}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)), \
                mock.patch.dict("os.environ", env), \
                mock.patch.object(publish, "build_publishers", return_value=({"instagram": ok, "facebook": Bad()}, {})), \
                mock.patch.object(publish.config, "load_settings", return_value={
                    "timezone": "America/Sao_Paulo", "publishing": {"instagram": True, "facebook": True}}):
            post = {**self.POST, "date": "2026-01-01"}  # já passou do horário
            state.save_queue([post])
            patch = publish.run(Path(tmp))
            res = patch["publish_results"][self.POST["id"]]
            self.assertIn("at", res["instagram"])
            self.assertEqual(res["facebook"]["error"], "token inválido")
            self.assertIn("/media/2026-10-09/2026-10-09-2-quiz/video_com_musica.mp4?v=2&exp=", ok.url)
            state.apply_patch(patch, date(2026, 1, 1), 30)
            saved = state.load_queue()[0]
            self.assertTrue(saved["published"]["instagram"])
            self.assertEqual(saved["publish_errors"]["facebook"]["attempts"], 1)
            # segunda rodada: Instagram não é repetido, Facebook tenta de novo
            patch2 = publish.run(Path(tmp))
            self.assertEqual(list(patch2["publish_results"][self.POST["id"]]), ["facebook"])

    def test_publish_now_single_platform_ignores_schedule(self):
        from app import publish

        class Ok:
            def supports(self, post): return True
            def publish(self, post, d, media_url): return "https://youtube.com/shorts/x"

        future = {**self.POST, "date": "2099-01-01"}
        settings = {"timezone": "America/Sao_Paulo",
                    "publishing": {"instagram": True, "facebook": True, "youtube": True}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)), \
                mock.patch.object(publish, "build_publishers", return_value=({"youtube": Ok()}, {})) as bp, \
                mock.patch.object(publish.config, "load_settings", return_value=settings):
            state.save_queue([future])
            self.assertEqual(publish.run(Path(tmp))["publish_results"], {})  # ainda não é a hora
            res = publish.run(Path(tmp), future["id"], "youtube", True)["publish_results"]
            self.assertEqual(list(res[future["id"]]), ["youtube"])
            self.assertEqual(bp.call_args[0][0], {"tiktok": False, "kwai": False, "youtube": True,
                                                  "instagram": False, "facebook": False})


class TikTokTests(unittest.TestCase):
    SECRET = "m" * 40

    def _resp(self, code, data):
        r = mock.Mock(status_code=code, text=json.dumps(data))
        r.json.return_value = data
        return r

    def test_inbox_upload_flow_and_token_rotation(self):
        from app.publishers import tiktok
        auth = {"open_id": "u1", "refresh_token_enc": tiktok.encrypt("old-refresh", self.SECRET)}
        calls = []

        def post(url, **kw):
            calls.append(url.split("/v2")[1])
            if url.endswith("/oauth/token/"):
                self.assertEqual(kw["data"]["refresh_token"], "old-refresh")
                return self._resp(200, {"access_token": "AT", "refresh_token": "new-refresh",
                                        "refresh_expires_in": 100})
            if url.endswith("/inbox/video/init/"):
                return self._resp(200, {"data": {"publish_id": "P1", "upload_url": "https://up"},
                                        "error": {"code": "ok"}})
            return self._resp(200, {"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}})

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(tiktok.requests, "post", side_effect=post), \
                mock.patch.object(tiktok.requests, "put", return_value=self._resp(201, {})) as put:
            Path(tmp, "video_sem_musica.mp4").write_bytes(b"x" * 1000)
            pub = tiktok.TikTokPublisher(auth, "ck", "cs", self.SECRET)
            out = pub.publish({"media": {"video_silent": "video_sem_musica.mp4"}}, Path(tmp), None)
            self.assertIn("rascunho", out)
            self.assertEqual(put.call_args.kwargs["headers"]["Content-Range"], "bytes 0-999/1000")
            self.assertEqual(tiktok.decrypt(pub.updated_auth["refresh_token_enc"], self.SECRET), "new-refresh")
            self.assertEqual(calls, ["/oauth/token/", "/post/publish/inbox/video/init/",
                                     "/post/publish/status/fetch/"])

    def test_not_connected_gives_clear_error(self):
        from app.publishers import PublishError, tiktok
        with self.assertRaisesRegex(PublishError, "Conectar TikTok"):
            tiktok.TikTokPublisher({}, "ck", "cs", self.SECRET)

    def test_image_posts_are_skipped(self):
        from app.publishers import tiktok
        pub = tiktok.TikTokPublisher.__new__(tiktok.TikTokPublisher)
        self.assertFalse(pub.supports({"media": {"images": ["a.jpg"]}}))


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
