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

    def test_youtube_daily_cap_skips_and_completes_post(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app import publish

        class Yt:
            def supports(self, post): return True
            def publish(self, post, d, media_url): return "https://youtube.com/shorts/NEW"

        now = datetime.now(ZoneInfo("America/Sao_Paulo"))
        stamp = now.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds")
        earlier = [{"id": f"old{i}", "date": now.date().isoformat(), "slot": 9 + i, "published": {"youtube": stamp}}
                   for i in range(2)]
        posts = [{**self.POST, "id": f"q{i}", "slot": i, "date": "2026-01-01"} for i in range(3)]
        env = {"PUBLIC_BASE_URL": "https://x.pages.dev", "MEDIA_SIGNING_SECRET": "s" * 40}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)), \
                mock.patch.dict("os.environ", env), \
                mock.patch.object(publish, "build_publishers", return_value=({"youtube": Yt()}, {})), \
                mock.patch.object(publish.config, "load_settings", return_value={
                    "timezone": "America/Sao_Paulo", "publishing": {"youtube": True, "youtube_max_per_day": 3}}):
            state.save_queue(posts)
            state.save_history(earlier)
            patch = publish.run(Path(tmp))
            res = patch["publish_results"]
            # 2 já enviados hoje + 1 agora = limite de 3; os outros 2 são pulados (sem erro)
            self.assertEqual(sum("at" in r["youtube"] for r in res.values()), 1)
            self.assertEqual(sum("skipped" in r["youtube"] for r in res.values()), 2)
            self.assertEqual(sorted(patch["completed"]), ["q0", "q1", "q2"])
            state.apply_patch({**patch, "completed": []}, date(2026, 1, 1), 30)
            saved = {p["id"]: p for p in state.load_queue()}
            skipped = [p for p in saved.values() if (p.get("publish_skipped") or {}).get("youtube")]
            self.assertEqual(len(skipped), 2)
            self.assertFalse(any(p.get("publish_errors") for p in skipped))
            # na rodada seguinte ninguém tenta o YouTube de novo
            self.assertEqual(publish.run(Path(tmp))["publish_results"], {})

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
                                                  "instagram": False, "facebook": False, "stories": False})


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


class ClearQueueTests(unittest.TestCase):
    def test_generate_now_clears_queue_keeps_history_and_new_ids(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app import generate
        settings = {"timezone": "America/Sao_Paulo", "approval": {"auto_approve": True},
                    "brand": {"handle": "@t"}, "groq": {"enabled": False},
                    "schedule": {"slots": [{"time": "00:01", "type": "verse"}, {"time": "23:59", "type": "curiosity"}]},
                    "video": {"video_types": ["quiz"]}}
        old_pub = {"id": "2026-10-10-1-verse", "date": "2026-10-10", "slot": 1, "time": "07:00", "status": "approved",
                   "published": {"instagram": "2026-10-10T10:00:00Z"}, "media": {"base": "x"}}
        old_pending = {"id": "2026-10-10-2-quiz", "date": "2026-10-10", "slot": 2, "time": "09:00",
                       "status": "pending", "published": {}, "media": {"base": "y"}}
        fake_media = {"base": "m/", "images": ["a.jpg"], "poster": "a.jpg", "duration": 0, "version": 1}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)), \
                mock.patch.object(generate.config, "load_settings", return_value=settings), \
                mock.patch.object(generate, "_render", return_value=fake_media):
            state.save_queue([old_pub, old_pending])
            args = generate.argparse.Namespace(date="2026-10-10", force=False, clear=True, no_groq=True,
                                               media_dir=tmp, out=str(Path(tmp, "p.json")))
            patch = generate.build(args)
            ids = [p["id"] for p in patch["posts"]]
            self.assertEqual(ids[0], "2026-10-10-1-verse-v2")  # não reaproveita o ID do post antigo
            state.apply_patch(patch, date(2026, 10, 10), 30)
            self.assertEqual(sorted(p["id"] for p in state.load_queue()), sorted(ids))
            hist = {p["id"]: p for p in state.load_history()}
            self.assertIn("2026-10-10-1-verse", hist)
            self.assertEqual(hist["2026-10-10-1-verse"]["published"]["instagram"], "2026-10-10T10:00:00Z")
            # horário já passou → não sai sozinho mesmo com aprovação automática
            now = datetime.now(ZoneInfo("America/Sao_Paulo"))
            if now.date().isoformat() == "2026-10-10":
                self.assertEqual(patch["posts"][0]["status"], "pending")


class CompletedPostsTests(unittest.TestCase):
    def test_fully_published_post_leaves_queue(self):
        from app import publish
        cfg = {"instagram": True, "facebook": True, "youtube": True}
        image = {"id": "a", "media": {"images": ["x.jpg"]}, "published": {"instagram": "t"}}
        video = {"id": "b", "media": {"video_music": "v.mp4"}, "published": {"instagram": "t", "facebook": "t"}}
        # imagem não vai pro YouTube: basta Instagram + Facebook
        self.assertEqual(publish.completed_posts([image], cfg, {"a": {"facebook": {"at": "t"}}}), ["a"])
        # vídeo ainda falta o YouTube (deu erro)
        self.assertEqual(publish.completed_posts([video], cfg, {"b": {"youtube": {"error": "x"}}}), [])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)):
            state.save_queue([{**image, "date": "2026-10-10", "slot": 1}, {**video, "date": "2026-10-10", "slot": 2}])
            state.apply_patch({"publish_results": {}, "completed": ["a"]}, date(2026, 10, 10), 0)
            self.assertEqual([p["id"] for p in state.load_queue()], ["b"])
            self.assertEqual(state.load_history()[0]["id"], "a")


class MetaErrorTests(unittest.TestCase):
    def test_error_190_without_page_permissions_explains_how_to_fix(self):
        from app.publishers import PublishError, meta
        resp = mock.Mock(status_code=400, text="", json=lambda: {"error": {
            "code": 190, "message": "Any of the pages_read_engagement,\n pages_show_list permission(s) must be granted"}})
        with mock.patch.object(meta.requests, "request", return_value=resp):
            with self.assertRaises(PublishError) as ctx:
                meta._call("GET", "me")
        self.assertIn("TODAS as permissões", str(ctx.exception))
        self.assertIn("META_ACCESS_TOKEN", str(ctx.exception))


class StoriesTests(unittest.TestCase):
    def test_story_uses_9x16_image_or_quiz_video(self):
        from app.publishers import meta
        calls = []

        def fake(method, path, **kw):
            calls.append((path, {k: v for k, v in kw.items() if k != "access_token"}))
            if path == "IG1/media":
                return {"id": "C1"}
            if path == "C1":
                return {"status_code": "FINISHED"}
            return {"id": "M1"}

        acc = meta.MetaAccount.__new__(meta.MetaAccount)
        acc.page_token, acc.ig_id, acc.page_id = "T", "IG1", "P1"
        pub = meta.InstagramStoryPublisher(acc)
        with mock.patch.object(meta, "_call", side_effect=fake):
            pub.publish({"media": {"images": ["imagem_story.jpg"]}}, Path("."), lambda f: "https://x/" + f)
            pub.publish({"media": {"video_music": "v.mp4", "images": []}}, Path("."), lambda f: "https://x/" + f)
        creates = [c[1] for c in calls if c[0] == "IG1/media"]
        self.assertEqual(creates[0], {"media_type": "STORIES", "image_url": "https://x/imagem_story.jpg"})
        self.assertEqual(creates[1], {"media_type": "STORIES", "video_url": "https://x/v.mp4"})


class MetricsTests(unittest.TestCase):
    def test_metrics_matched_to_posts_and_missing_permission_is_reported(self):
        from app import metrics
        from app.publishers import PublishError, meta
        post = {"id": "2026-10-10-2-quiz", "date": "2026-10-10", "time": "09:00", "type": "quiz",
                "content": {"question": "Quem?"},
                "publish_links": {"instagram": "https://www.instagram.com/reel/AAA/",
                                  "facebook": "https://www.facebook.com/P1/videos/V9",
                                  "youtube": "https://youtube.com/shorts/YT1"}}

        def fake_get(url, **params):
            if url.endswith("/IG1/media"):
                return {"data": [{"id": "M1", "permalink": "https://www.instagram.com/reel/AAA/",
                                  "media_product_type": "REELS", "like_count": 7, "comments_count": 2}]}
            if url.endswith("/insights"):
                raise PublishError("(#10) permission")
            if url.endswith("/posts"):
                return {"data": []}
            if url.endswith("/videos"):
                return {"data": [{"id": "V9", "likes": {"summary": {"total_count": 3}},
                                  "comments": {"summary": {"total_count": 1}}}]}
            raise AssertionError(url)

        acc = mock.Mock(ig_id="IG1", page_id="P1", page_token="T")
        env = {"META_ACCESS_TOKEN": "T"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)), \
                mock.patch.dict("os.environ", env, clear=False), \
                mock.patch.object(meta, "MetaAccount", return_value=acc), \
                mock.patch.object(metrics, "_get", side_effect=fake_get), \
                mock.patch.object(metrics, "collect_youtube", return_value={"YT1": {"views": 64, "likes": 5}}):
            state.save_history([post])
            data = metrics.collect(date(2026, 10, 10))
        row = data["posts"][post["id"]]
        self.assertEqual(row["instagram"], {"likes": 7, "comments": 2})
        self.assertEqual(row["facebook"], {"likes": 3, "comments": 1})
        self.assertEqual(row["youtube"]["views"], 64)
        self.assertTrue(any("instagram_manage_insights" in n for n in data["notes"]))


class CompilationTests(unittest.TestCase):
    """Vídeo longo de quiz (YouTube): escolha das perguntas, regras de publicação e legendas."""

    def test_pick_fills_about_ten_minutes_without_repeating_questions(self):
        from app import compilation
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)):
            state.save_queue([])
            items, updates = compilation.pick_quizzes(TODAY, state.load_used(), random.Random(1), 600, [])
            total = sum(compilation.clip_timeline(i)["total"] for i in items) + 16
            self.assertTrue(570 <= total <= 620, total)
            keys = [i["ref_key"] for i in items]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(set(updates["compilation"]), set(keys))
            # o que vem do banco passa a contar como usado (os posts diários não repetem)
            self.assertTrue(set(updates["quiz"]) <= {i["id"] for i in items})

    def test_recent_posted_quizzes_come_first_and_old_compilation_questions_are_skipped(self):
        from app import compilation
        raw = validate.load_bank("quiz")[0]
        post = {"id": "2026-10-08-2-quiz", "date": "2026-10-08", "slot": 2, "type": "quiz", "status": "approved",
                "content": {k: raw[k] for k in ("question", "options", "answer", "ref", "evidence", "difficulty")}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)):
            state.save_queue([post])
            items, _ = compilation.pick_quizzes(TODAY, state.load_used(), random.Random(2), 600, [])
            self.assertIn("recent", {i["source"] for i in items})
            key = validate.validate("quiz", dict(raw))["ref_key"]
            used = {**state.load_used(), "compilation": {key: "2026-10-01"}}
            items, _ = compilation.pick_quizzes(TODAY, used, random.Random(2), 600, [])
            self.assertNotIn(key, [i["ref_key"] for i in items])

    def test_only_youtube_gets_the_long_video(self):
        from app import publish
        post = {"id": "c", "type": "compilation", "media": {"video_music": "video_longo.mp4", "images": []}}
        self.assertTrue(publish.applies("youtube", post))
        for net in ("instagram", "facebook", "stories", "tiktok"):
            self.assertFalse(publish.applies(net, post), net)
        cfg = {"instagram": True, "facebook": True, "stories": True, "youtube": True}
        self.assertEqual(publish.completed_posts([{**post, "published": {}}], cfg, {"c": {"youtube": {"at": "t"}}}), ["c"])

    def test_youtube_upload_returns_watch_link_and_sets_thumbnail(self):
        from app.publishers import youtube
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp)
            (media / "video_longo.mp4").write_bytes(b"x")
            (media / "miniatura.jpg").write_bytes(b"y")
            pub = youtube.YouTubePublisher.__new__(youtube.YouTubePublisher)
            pub.token = "T"
            calls = []

            def fake_post(url, **kw):
                calls.append(("POST", url, kw.get("json"), kw.get("params")))
                return mock.Mock(status_code=200, headers={"Location": "https://up/1"}, text="")

            with mock.patch.object(youtube.requests, "post", side_effect=fake_post), \
                    mock.patch.object(youtube.requests, "put", return_value=mock.Mock(status_code=200, json=lambda: {"id": "VID1"})):
                post = {"type": "compilation", "captions": {"youtube": {"title": "T", "description": "D"}},
                        "media": {"video_music": "video_longo.mp4", "thumbnail": "miniatura.jpg"}}
                self.assertEqual(pub.publish(post, media, None), "https://youtu.be/VID1")
            self.assertEqual(calls[0][2]["snippet"]["categoryId"], "27")
            self.assertNotIn("#shorts", calls[0][2]["snippet"]["title"])
            self.assertEqual(calls[1][3], {"videoId": "VID1"})

    def test_captions_have_valid_youtube_chapters(self):
        from app import compilation
        chapters = [(0.0, "Introdução")] + [(7 + 14 * i, f"Pergunta {i + 1}") for i in range(40)]
        yt = compilation.youtube_captions(40, 10, chapters, "@teste")
        self.assertLessEqual(len(yt["title"]), 100)
        lines = [ln for ln in yt["description"].splitlines() if ln[:1].isdigit()]
        self.assertTrue(lines[0].startswith("0:00 "))
        self.assertIn("0:07 Pergunta 1", lines)
        self.assertIn("9:13 Pergunta 40", lines)
        self.assertIn("domínio público", yt["description"])

    def test_metrics_understands_long_video_links(self):
        from app.metrics import YT_ID
        for link, vid in (("https://youtu.be/ABC_-1", "ABC_-1"), ("https://youtube.com/shorts/XYZ", "XYZ"),
                          ("https://www.youtube.com/watch?v=Q9", "Q9")):
            self.assertEqual(YT_ID.search(link).group(1), vid)

    def test_generate_skips_compilation_when_not_the_configured_weekday(self):
        from app import generate
        settings = {**SETTINGS, "schedule": {"slots": [{"time": "07:00", "type": "verse"}]},
                    "compilation": {"enabled": True, "weekday": 6}}
        patch = {"used": {}}
        # 2026-10-09 é sexta; o vídeo longo está configurado para domingo
        self.assertIsNone(generate._compilation_post(settings, TODAY, {}, Path("x"), {}, set(), False, patch, 2))
        # falha ao montar nunca derruba a geração diária
        sunday = date(2026, 10, 11)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "STATE_DIR", Path(tmp)), \
                mock.patch.object(generate.compilation, "build_post", side_effect=RuntimeError("ffmpeg")):
            self.assertIsNone(generate._compilation_post(settings, sunday, {}, Path(tmp), {}, set(), False, patch, 2))


class UpgradesTests(unittest.TestCase):
    def test_curiosity_video_only_when_enabled(self):
        from app import generate
        self.assertTrue(generate._has_video("quiz", {}))
        self.assertFalse(generate._has_video("curiosity", {"video": {"video_types": ["quiz"]}}))
        self.assertTrue(generate._has_video("curiosity", {"video": {"video_types": ["quiz", "curiosity"]}}))
        self.assertFalse(generate._has_video("verse", {"video": {"video_types": ["quiz", "curiosity"]}}))

    def test_alert_only_on_first_and_last_attempt(self):
        from app import alert
        patch = {"publish_results": {"p1": {"instagram": {"error": "x"}, "facebook": {"at": "t", "url": "u"}},
                                     "p2": {"youtube": {"error": "y"}}}}
        queue = [{"id": "p1", "publish_errors": {"instagram": {"attempts": 1}}},
                 {"id": "p2", "publish_errors": {"youtube": {"attempts": 2}}}]
        found = alert.problems(patch, queue, 3)
        self.assertEqual(len(found), 1)
        self.assertIn("Instagram", found[0])
        queue[1]["publish_errors"]["youtube"]["attempts"] = 3
        found = alert.problems(patch, queue, 3)
        self.assertEqual(len(found), 2)
        self.assertIn("DESISTIU", found[1])
        self.assertEqual(alert.problems({"publish_results": {"p1": {"facebook": {"at": "t"}}}}, queue, 3), [])

    def test_weekly_report_has_best_hour_top_posts_and_links(self):
        from app import report
        posts = {}
        for i, (t, likes) in enumerate([("09:00", 1), ("09:00", 3), ("21:00", 20), ("21:00", 30), ("12:00", 5)]):
            posts[f"p{i}"] = {"type": "quiz", "date": "2026-10-08", "time": t, "title": f"Post {i}",
                              "links": {"instagram": f"https://ig/{i}"}, "instagram": {"likes": likes, "comments": 0}}
        posts["old"] = {"type": "quiz", "date": "2026-08-01", "time": "07:00", "title": "Velho", "instagram": {"likes": 999}}
        text = report.build({"posts": posts, "notes": ["falta permissão"]}, date(2026, 10, 12), "fulano")
        self.assertIn("@fulano", text)
        self.assertIn("Melhor: **21:00**", text)
        self.assertIn("Mais fraco: **09:00**", text)  # 12:00 tem só 1 post: fica de fora
        self.assertIn("[instagram](https://ig/3)", text.split("Os 3 melhores")[1].split("\n")[2])
        self.assertNotIn("Velho", text)
        self.assertIn("falta permissão", text)
        self.assertIsNone(report.build({"posts": {}}, date(2026, 10, 12)))


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
