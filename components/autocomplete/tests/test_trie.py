from __future__ import annotations

import random
import unittest

from pulsegrid_autocomplete import (
    AutocompleteInputError,
    IndexLimits,
    IndexSnapshot,
    Suggestion,
    Trie,
    normalize_label,
    suggestion_order,
)


def suggestion(resource_id: int, kind: str, label: str) -> Suggestion:
    return Suggestion(str(resource_id), kind, label)  # type: ignore[arg-type]


class TrieContractTests(unittest.TestCase):
    def test_empty_index_and_missing_prefix(self) -> None:
        trie = Trie()
        self.assertEqual((), trie.search("missing", kinds=("doctor",)))
        with self.assertRaises(AutocompleteInputError):
            trie.search("   ")

    def test_unicode_nfkc_casefold_and_whitespace(self) -> None:
        trie = Trie()
        trie.insert(suggestion(1, "doctor", "  ＡＬＩＣＥ\tVan   Dyke "))
        trie.insert(suggestion(2, "doctor", "Straße Clinic"))
        self.assertEqual(
            (suggestion(1, "doctor", "  ＡＬＩＣＥ\tVan   Dyke "),),
            trie.search("alice van", kinds=("doctor",)),
        )
        self.assertEqual(
            (suggestion(2, "doctor", "Straße Clinic"),),
            trie.search("STRASSE", kinds=("doctor",)),
        )
        self.assertEqual("alice van dyke", normalize_label("ＡＬＩＣＥ\tVan   Dyke"))

    def test_duplicate_identity_replaces_rename_and_preserves_other_ties(self) -> None:
        trie = Trie()
        trie.insert(suggestion(10, "doctor", "Mira Patel"))
        trie.insert(suggestion(2, "doctor", "Mira Patel"))
        trie.insert(suggestion(10, "doctor", "Mira Shah"))
        self.assertEqual(
            (suggestion(2, "doctor", "Mira Patel"),),
            trie.search("mira pat", kinds=("doctor",)),
        )
        self.assertEqual(
            (suggestion(10, "doctor", "Mira Shah"),),
            trie.search("mira sh", kinds=("doctor",)),
        )
        trie.remove("doctor", "2")
        self.assertEqual((), trie.search("mira pat", kinds=("doctor",)))

    def test_deterministic_order_kind_then_numeric_id_and_kind_filtering(self) -> None:
        values = [
            suggestion(20, "doctor", "A. Name"),
            suggestion(3, "doctor", "A. Name"),
            suggestion(1, "specialty", "A. Name"),
            suggestion(9, "medicine", "A. Name"),
        ]
        first = Trie()
        second = Trie()
        for item in values:
            first.insert(item)
        for item in reversed(values):
            second.insert(item)
        expected = (
            suggestion(3, "doctor", "A. Name"),
            suggestion(20, "doctor", "A. Name"),
            suggestion(9, "medicine", "A. Name"),
            suggestion(1, "specialty", "A. Name"),
        )
        self.assertEqual(expected, first.search("a.", limit=20))
        self.assertEqual(expected, second.search("Ａ．", limit=20))
        self.assertEqual(
            (suggestion(3, "doctor", "A. Name"),),
            first.search("a.", limit=1, kinds=("doctor",)),
        )

    def test_limits_and_prefix_bounds(self) -> None:
        trie = Trie()
        for resource_id in range(1, 31):
            trie.insert(suggestion(resource_id, "medicine", "alpha"))
        self.assertEqual(20, len(trie.search("a", limit=20, kinds=("medicine",))))
        with self.assertRaises(AutocompleteInputError):
            trie.search("a", limit=21)
        with self.assertRaises(AutocompleteInputError):
            trie.search("a" * 101)

    def test_removing_cached_top_entries_promotes_next_exact_candidates(self) -> None:
        trie = Trie()
        for resource_id in range(1, 26):
            trie.insert(suggestion(resource_id, "specialty", "Cardiology"))
        self.assertEqual(tuple(str(value) for value in range(1, 21)), tuple(
            item.id for item in trie.search("card", limit=20, kinds=("specialty",))
        ))
        for resource_id in range(1, 6):
            trie.remove("specialty", str(resource_id))
        self.assertEqual(tuple(str(value) for value in range(6, 26)), tuple(
            item.id for item in trie.search("card", limit=20, kinds=("specialty",))
        ))

    def test_remove_prunes_and_update_inserts_new_path(self) -> None:
        trie = Trie()
        trie.insert(suggestion(1, "medicine", "acetaminophen"))
        trie.insert(suggestion(2, "medicine", "acetanilide"))
        before = trie.node_count
        trie.insert(suggestion(1, "medicine", "ibuprofen"))
        self.assertEqual(1, len(trie.search("acet", kinds=("medicine",))))
        self.assertEqual("ibuprofen", trie.search("ibu", kinds=("medicine",))[0].label)
        trie.remove("medicine", "2")
        self.assertGreater(before, trie.node_count)
        self.assertEqual((), trie.search("acetan", kinds=("medicine",)))

    def test_snapshot_seals_live_tree(self) -> None:
        trie = Trie()
        trie.insert(suggestion(1, "specialty", "Cardiology"))
        snapshot = IndexSnapshot(7, trie)
        self.assertEqual(7, snapshot.generation)
        self.assertTrue(trie.sealed)
        with self.assertRaises(RuntimeError):
            trie.insert(suggestion(2, "specialty", "Cardiac Surgery"))

    def test_large_synthetic_catalog_exact_top_k(self) -> None:
        trie = Trie()
        expected: list[Suggestion] = []
        for index in range(1, 20_001):
            label = f"Dr. Aanya Iyer {index:06d}"
            value = suggestion(index, "doctor", label)
            trie.insert(value)
            if index <= 20:
                expected.append(value)
        self.assertEqual(
            tuple(expected), trie.search("dr. aanya", limit=20, kinds=("doctor",))
        )
        self.assertGreater(trie.node_count, 0)
        self.assertGreater(trie.estimated_bytes(), 0)

    def test_randomized_insert_order_matches_frozen_oracle(self) -> None:
        rng = random.Random(404)
        entries = [
            suggestion(index, "medicine", f"Compound {rng.randrange(20):02d} {index:05d}")
            for index in range(1, 501)
        ]
        forward = Trie()
        shuffled = Trie()
        for entry in entries:
            forward.insert(entry)
        shuffled_entries = entries.copy()
        rng.shuffle(shuffled_entries)
        for entry in shuffled_entries:
            shuffled.insert(entry)
        for prefix in ("c", "compound 0", "compound 03 00", "missing"):
            normalized_prefix = normalize_label(prefix)
            for limit in (10, 20):
                expected = tuple(
                    sorted(
                        (
                            entry
                            for entry in entries
                            if normalize_label(entry.label).startswith(normalized_prefix)
                        ),
                        key=suggestion_order,
                    )[:limit]
                )
                self.assertEqual(
                    expected,
                    forward.search(prefix, limit=limit, kinds=("medicine",)),
                )
                self.assertEqual(
                    expected,
                    shuffled.search(prefix, limit=limit, kinds=("medicine",)),
                )


if __name__ == "__main__":
    unittest.main()
