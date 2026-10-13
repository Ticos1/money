"""Testes do calendário cristão, do formato 'Em qual livro está?' e da análise de métricas."""
import random
import unittest
from datetime import date, timedelta

from app import bible, captions, datas, derived, report, validate
from tests.test_core import SETTINGS, FakeGroq


class CalendarTests(unittest.TestCase):
    def test_easter_known_dates(self):
        self.assertEqual(datas.easter(2025), date(2025, 4, 20))
        self.assertEqual(datas.easter(2026), date(2026, 4, 5))
        self.assertEqual(datas.easter(2027), date(2027, 3, 28))

    def test_special_days(self):
        self.assertEqual(datas.theme_for(date(2026, 12, 25)).key, "natal")
        self.assertEqual(datas.theme_for(date(2026, 4, 3)).key, "sextasanta")
        self.assertEqual(datas.theme_for(date(2026, 4, 5)).key, "pascoa")
        self.assertEqual(datas.theme_for(date(2026, 5, 24)).key, "pentecostes")
        self.assertEqual(datas.theme_for(date(2026, 5, 10)).key, "maes")
        self.assertEqual(datas.theme_for(date(2026, 8, 9)).key, "pais")
        self.assertEqual(datas.theme_for(date(2026, 10, 12)).key, "crianca")
        self.assertEqual(datas.theme_for(date(2026, 10, 31)).key, "reforma")
        self.assertEqual(datas.theme_for(date(2026, 12, 13)).key, "biblia")
        self.assertEqual(datas.theme_for(date(2026, 10, 18)).key, "domingo")  # domingo comum
        self.assertIsNone(datas.theme_for(date(2026, 10, 14)))

    def test_every_special_day_has_fresh_themed_content_in_the_bank(self):
        """Cada data tem versículo, quiz e curiosidade do tema (domingo: só versículo)."""
        themes = [datas.NATAL, datas.ANO_NOVO, datas.SEXTA_SANTA, datas.PASCOA, datas.PENTECOSTES,
                  datas.MAES, datas.PAIS, datas.CRIANCA, datas.REFORMA, datas.BIBLIA, datas.DOMINGO]
        for theme in themes:
            for kind in theme.kinds:
                items = [validate.validate(kind, i) for i in validate.load_bank(kind)]
                n = sum(1 for i in items if datas.matches(theme, i))
                self.assertGreaterEqual(n, 3 if kind != "curiosity" else 1, f"{theme.key}/{kind}: {n}")

    def test_prefer_only_applies_on_special_days_and_when_there_is_content(self):
        fresh = [{"id": "a", "tags": ["natal"]}, {"id": "b", "tags": ["paz"]}]
        out, theme = datas.prefer("verse", date(2026, 12, 25), fresh)
        self.assertEqual([i["id"] for i in out], ["a"])
        self.assertEqual(theme.key, "natal")
        out, theme = datas.prefer("verse", date(2026, 10, 14), fresh)  # dia comum
        self.assertEqual(len(out), 2)
        self.assertIsNone(theme)
        out, theme = datas.prefer("verse", date(2026, 5, 10), fresh)  # sem item do tema: segue normal
        self.assertEqual(len(out), 2)
        self.assertIsNone(theme)

    def test_date_hook_goes_into_captions(self):
        item = {"id": "v1", "ref": "Lucas 2:11", "ref_label": "Lucas 2:11", "verse_text": "x",
                "reflection": "r", "on_screen": "o", "tags": ["natal"], "date_hook": datas.NATAL.hook}
        caps, _ = captions.build("verse", item, SETTINGS, FakeGroq([]), random.Random(1), [])
        self.assertIn("Feliz Natal", caps["instagram"])
        self.assertIn("Feliz Natal", caps["tiktok"])


class BookFormatTests(unittest.TestCase):
    def test_book_question_has_one_right_answer_from_same_testament(self):
        for seed in range(40):
            item, upd = derived.pick("book", date(2026, 10, 14), {}, None, {}, random.Random(seed), [])
            self.assertIn(item["id"], upd["book"])
            self.assertEqual(len(set(item["options"])), 4)
            self.assertEqual(item["options"][item["answer"]], bible.BOOK_NAMES[bible.parse_reference(item["ref"]).book])
            ot = [n for c, n, _ in bible.BOOKS[:39]]
            self.assertEqual(all(o in ot for o in item["options"]), item["options"][item["answer"]] in ot)

    def test_verses_repeated_elsewhere_in_the_bible_are_rejected(self):
        # "O SENHOR disse a Moisés:" aparece dezenas de vezes: não pode virar pergunta de livro
        dup = next(t for t, n in derived._text_counts().items() if n > 5 and len(t) > 20)
        raw = next(v for ch in bible._data().values() for vs in ch.values() for v in vs
                   if bible.normalize(v) == dup)
        item = {"ref": "Êxodo 6:10", "verse_text": raw}
        self.assertIsNone(derived.make_book(item, random.Random(1)))

    def test_book_captions(self):
        item, _ = derived.pick("book", date(2026, 10, 14), {}, None, {}, random.Random(3), [])
        caps, src = captions.build("book", item, SETTINGS, FakeGroq([]), random.Random(1), [])
        self.assertEqual(src, "template")
        self.assertIn("A)", caps["instagram"])
        self.assertNotIn(item["book_name"] + " " + item["ref"].split()[-1], caps["instagram"])  # sem a referência


class AnalysisTests(unittest.TestCase):
    def test_analysis_over_whole_history(self):
        posts = {
            "a": {"type": "quiz", "date": "2026-10-10", "time": "08:00", "instagram": {"likes": 5, "reach": 40}},
            "b": {"type": "curiosity", "date": "2026-10-11", "time": "12:00", "instagram": {"likes": 0, "reach": 0}},
        }
        text = report.analyze({"posts": posts})
        self.assertIn("Desafio de quiz", text)
        self.assertIn("08:00", text)
        self.assertIn("Posts com alcance zero: **1** de 2", text)
        self.assertLess(text.index("Desafio de quiz"), text.index("Você sabia?"))  # melhor primeiro
        self.assertIsNone(report.analyze({"posts": {}}))


if __name__ == "__main__":
    unittest.main()
