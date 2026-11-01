from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from english_metrics import edit_distance, lexical_pair, score_records, tokenize


def parser(text):
    """Tiny test parser, independent of the production renderer."""
    if text == "Cannot answer.":
        return {"answerable": False, "rows": None}
    if text.startswith("The result is ") and text.endswith("."):
        return {"answerable": True, "rows": [[text[len("The result is "):-1]]]}
    raise ValueError("Not a controlled answer")


def canonicalizer(rows):
    return sorted(tuple(row) for row in rows)


class LexicalTests(unittest.TestCase):
    def test_numbers_signs_decimals_and_negation_are_retained(self):
        self.assertEqual(tokenize("No dose: -3.50 mg."), ["no", "dose:", "-3.50", "mg."])
        for reference, prediction in (("There are 3 admissions.", "There are 4 admissions."),
                                      ("The result is -3.5.", "The result is 3.5."),
                                      ("The patient did not die.", "The patient did die.")):
            scores = lexical_pair(reference, prediction)
            self.assertFalse(scores["normalized_EM"])
            self.assertGreater(scores["edit_distance"], 0)

    def test_only_case_unicode_and_whitespace_are_normalized(self):
        scores = lexical_pair("The  result is ３.\n", "the result is 3.")
        self.assertTrue(scores["normalized_EM"])
        self.assertFalse(scores["raw_EM"])
        self.assertFalse(lexical_pair("3", "3.")["normalized_EM"])

    def test_duplicate_tokens_use_multiset_counts(self):
        scores = lexical_pair("A A B", "A B B")
        self.assertEqual(scores["matched_tokens"], 2)
        self.assertAlmostEqual(scores["token_F1"], 2 / 3)

    def test_rouge_detects_order_where_bag_f1_does_not(self):
        scores = lexical_pair("A B C", "C B A")
        self.assertEqual(scores["token_F1"], 1)
        self.assertAlmostEqual(scores["ROUGE_L_F1"], 1 / 3)

    def test_wer_can_exceed_one_hundred(self):
        report = score_records([{"id": "x", "output_text": "one"}],
                               {"x": "one two three four"}, controlled=False)
        self.assertEqual(report["lexical"]["WER"], 300)

    def test_corpus_wer_is_not_average_sentence_wer(self):
        refs = [{"id": "x", "output_text": "a"}, {"id": "y", "output_text": "b c d e"}]
        report = score_records(refs, {"x": "z", "y": "b c d e"}, controlled=False)
        self.assertEqual(report["lexical"]["WER"], 20)
        self.assertEqual(report["lexical"]["normalized_EM"], 50)

    def test_empty_output_stays_in_denominator(self):
        report = score_records([{"id": "x", "output_text": "three admissions"}],
                               {"x": ""}, controlled=False)
        self.assertEqual(report["n"], 1)
        self.assertEqual(report["lexical"]["WER"], 100)
        self.assertEqual(report["lexical"]["token_F1_macro"], 0)

    def test_empty_reference_wer_is_undefined_with_insertions(self):
        report = score_records([{"id": "x", "output_text": ""}], {"x": "x"}, controlled=False)
        self.assertIsNone(report["lexical"]["WER"])

    def test_edit_distance_substitution_insertion_deletion(self):
        self.assertEqual(edit_distance(["a", "b", "c"], ["a", "d", "c", "e"]), 2)
        self.assertEqual(edit_distance(["a", "b"], []), 2)


class IntegrityTests(unittest.TestCase):
    def test_missing_extra_duplicate_null_and_empty_datasets_rejected(self):
        refs = [{"id": "x", "output_text": "result"}]
        for predictions in ({"y": "result"}, [{"id": "x", "output_text": "result"}] * 2,
                            {"x": None}, {}):
            with self.assertRaises(ValueError):
                score_records(refs, predictions, controlled=False)
        with self.assertRaises(ValueError):
            score_records([], {}, controlled=False)

    def test_duplicate_references_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate ID"):
            score_records([{"id": "x", "output_text": "a"}] * 2,
                          {"x": "a"}, controlled=False)

    def test_prediction_embedded_id_disagreement_rejected(self):
        with self.assertRaisesRegex(ValueError, "ID disagree"):
            score_records([{"id": "x", "output_text": "a"}],
                          {"x": {"id": "y", "output_text": "a"}}, controlled=False)


class ControlledTests(unittest.TestCase):
    def refs(self):
        return [{"id": "a", "output_text": "The result is 3.", "answerable": True,
                 "result_rows": [["3"]]},
                {"id": "u", "output_text": "Cannot answer.", "answerable": False,
                 "result_rows": None}]

    def score(self, predictions):
        return score_records(self.refs(), predictions, controlled_parser=parser,
                             canonicalizer=canonicalizer)

    def test_correct_answers_and_abstentions_separate_groups(self):
        report = self.score({"a": "The result is 3.", "u": "Cannot answer."})
        self.assertEqual(report["controlled"]["fact_EM"], 100)
        self.assertEqual(report["controlled"]["parse_coverage"], 100)
        self.assertEqual(report["groups"]["answerable"]["n"], 1)
        self.assertEqual(report["groups"]["unanswerable"]["n"], 1)

    def test_wrong_number_high_lexical_score_still_fails_facts(self):
        report = self.score({"a": "The result is 4.", "u": "Cannot answer."})
        self.assertGreater(report["lexical"]["token_F1_macro"], 80)
        self.assertEqual(report["controlled"]["fact_EM"], 50)

    def test_non_template_prose_fails_with_parse_coverage(self):
        report = self.score({"a": "Three is the answer.", "u": "Cannot answer."})
        self.assertEqual(report["controlled"]["parse_coverage"], 50)
        self.assertEqual(report["controlled"]["fact_EM"], 50)

    def test_self_reported_rows_cannot_override_wrong_text(self):
        report = self.score({"a": {"output_text": "The result is 4.", "result_rows": [["3"]]},
                             "u": "Cannot answer."})
        self.assertEqual(report["controlled"]["fact_EM"], 50)

    def test_wrong_abstention_and_fabricated_answer_fail(self):
        report = self.score({"a": "Cannot answer.", "u": "The result is 3."})
        self.assertEqual(report["controlled"]["fact_EM"], 0)
        self.assertEqual(report["controlled"]["parse_coverage"], 100)

    def test_missing_controlled_reference_fields_rejected(self):
        with self.assertRaisesRegex(ValueError, "answerable and result_rows"):
            score_records([{"id": "a", "output_text": "The result is 3."}],
                          {"a": "The result is 3."}, controlled_parser=parser,
                          canonicalizer=canonicalizer)


class ProductionControlledTests(unittest.TestCase):
    def score_rows(self, real, predicted, *, answerable=True):
        from reference_renderer import render_answer
        refs = [{"id": "x", "output_text": render_answer(real, answerable=answerable),
                 "answerable": answerable, "result_rows": real}]
        return score_records(refs, {"x": predicted})

    def test_roundtrip_multi_column_duplicates_and_null(self):
        from reference_renderer import render_answer
        rows = [["lab", "3.12345"], ["lab", None], ["lab", None]]
        report = self.score_rows(rows, render_answer(rows))
        self.assertEqual(report["controlled"]["fact_EM"], 100)

    def test_dropping_duplicate_result_row_fails(self):
        from reference_renderer import render_answer
        report = self.score_rows([["x"], ["x"]], render_answer([["x"]]))
        self.assertEqual(report["controlled"]["fact_EM"], 0)
        self.assertEqual(report["controlled"]["parse_coverage"], 100)

    def test_sql_null_is_not_unanswerable(self):
        from reference_renderer import ABSTENTION_TEXT
        report = self.score_rows([[None]], ABSTENTION_TEXT)
        self.assertEqual(report["controlled"]["fact_EM"], 0)

    def test_extra_contradictory_prose_is_never_silently_ignored(self):
        from reference_renderer import render_answer
        text = render_answer([["3"]]) + " This proves the patient had no admissions."
        report = self.score_rows([["3"]], text)
        self.assertEqual(report["controlled"]["fact_EM"], 0)
        self.assertEqual(report["controlled"]["parse_coverage"], 0)

    def test_malformed_json_and_nested_payloads_are_failed_outputs(self):
        for text in ('The returned value is {"x": 3}.',
                     'The returned value is ["3"].',
                     'The returned value is {oops}.',
                     'The query returned 1 rows.\nRow 1: 3.',
                     'The returned value is ' + '[' * 2000 + '"3"' + ']' * 2000 + '.'):
            with self.subTest(text=text[:50]):
                report = self.score_rows([["3"]], text)
                self.assertEqual(report["controlled"]["fact_EM"], 0)
                self.assertEqual(report["controlled"]["parse_coverage"], 0)

    def test_canonical_three_decimal_numeric_values_not_free_word_similarity(self):
        from reference_renderer import render_answer
        report = self.score_rows([["3.12349"]], render_answer([["3.12340"]]))
        self.assertEqual(report["controlled"]["fact_EM"], 100)
        report = self.score_rows([["3.12349"]], render_answer([["3.124"]]))
        self.assertEqual(report["controlled"]["fact_EM"], 0)

    def test_column_order_and_extra_facts_are_significant(self):
        from reference_renderer import render_answer
        for rows in ([["b", "a"]], [["a", "b"], ["extra", "fact"]]):
            report = self.score_rows([["a", "b"]], render_answer(rows))
            self.assertEqual(report["controlled"]["fact_EM"], 0)

    def test_full_result_not_first_hundred_rows(self):
        from reference_renderer import render_answer
        rows = [[str(n)] for n in range(101)]
        report = self.score_rows(rows, render_answer(rows[:100]))
        self.assertEqual(report["controlled"]["fact_EM"], 0)

    def test_invalid_gold_reference_stops_rather_than_becoming_prediction_error(self):
        with self.assertRaises(ValueError):
            score_records([{"id": "x", "answerable": False, "result_rows": [["3"]],
                            "output_text": "Cannot answer."}], {"x": "Cannot answer."})


if __name__ == "__main__":
    unittest.main()
