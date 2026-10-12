"""Unicode-normalized, top-K-cached radix trie for immutable search snapshots."""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from heapq import merge
from itertools import islice
from types import MappingProxyType
from typing import Iterable, Literal, Mapping, Sequence

from .errors import AutocompleteInputError

SuggestionKind = Literal["doctor", "specialty", "medicine"]
KINDS: tuple[SuggestionKind, ...] = ("doctor", "specialty", "medicine")
MAX_PREFIX_CODEPOINTS = 100
MAX_RESULT_LIMIT = 20
DEFAULT_RESULT_LIMIT = 10
MAX_ID = 9_223_372_036_854_775_807
_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,18}$")


def normalize_label(value: str) -> str:
    """Apply the frozen Unicode NFKC/casefold/whitespace normalization."""
    if not isinstance(value, str):
        raise AutocompleteInputError("label must be text")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def normalize_prefix(value: str) -> str:
    """Normalize and validate a literal prefix; autocomplete has no fuzzy mode."""
    normalized = normalize_label(value)
    if not normalized or len(normalized) > MAX_PREFIX_CODEPOINTS:
        raise AutocompleteInputError("prefix length is outside the supported range")
    return normalized


def normalize_kinds(kinds: Sequence[str] | None) -> tuple[SuggestionKind, ...]:
    """Validate, sort, and de-duplicate kinds using the owner allowlist."""
    if kinds is None:
        return KINDS
    selected = set(kinds)
    if not selected or any(kind not in KINDS for kind in selected):
        raise AutocompleteInputError("unknown or empty suggestion kind")
    return tuple(sorted(selected))  # type: ignore[return-value]


def validate_limit(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= MAX_RESULT_LIMIT:
        raise AutocompleteInputError("limit must be between 1 and 20")
    return limit


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A safe owner-directory/catalog reference and its original display label."""

    id: str
    kind: SuggestionKind
    label: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not _ID_PATTERN.fullmatch(self.id)
            or int(self.id) > MAX_ID
        ):
            raise AutocompleteInputError("suggestion id must be a positive BIGINT string")
        if self.kind not in KINDS:
            raise AutocompleteInputError("unknown suggestion kind")
        if not isinstance(self.label, str) or not normalize_label(self.label):
            raise AutocompleteInputError("suggestion label must contain visible text")


def suggestion_key(suggestion: Suggestion) -> tuple[str, str]:
    return suggestion.kind, suggestion.id


def suggestion_order(suggestion: Suggestion) -> tuple[str, str, int]:
    return normalize_label(suggestion.label), suggestion.kind, int(suggestion.id)


def rank_suggestions(
    suggestions: Iterable[Suggestion], limit: int
) -> tuple[Suggestion, ...]:
    """Suppress duplicate source IDs and apply the contract's deterministic order."""
    validate_limit(limit)
    unique: dict[tuple[str, str], Suggestion] = {}
    for suggestion in suggestions:
        key = suggestion_key(suggestion)
        current = unique.get(key)
        if current is None or suggestion_order(suggestion) < suggestion_order(current):
            unique[key] = suggestion
    return tuple(sorted(unique.values(), key=suggestion_order)[:limit])


class _Node:
    """A compressed radix node; candidates is the exact best 20 below this node."""

    __slots__ = ("edge", "children", "terminals", "candidates")

    def __init__(self, edge: str = "") -> None:
        self.edge = edge
        self.children: dict[str, _Node] | Mapping[str, _Node] = {}
        self.terminals: dict[tuple[str, str], Suggestion] | Mapping[
            tuple[str, str], Suggestion
        ] = {}
        self.candidates: tuple[_RankedCandidate, ...] = ()


_RankedCandidate = tuple[str, str, int, Suggestion]


class Trie:
    """Mutable builder which becomes immutable when placed in an IndexSnapshot.

    The radix representation compresses unary character paths. Each explicit node
    retains at most 20 candidates per kind, allowing exact top-K queries with kind
    filtering while bounding query enumeration independently of catalog size.
    """

    __slots__ = ("_roots", "_entries", "_normalized_labels", "_node_count", "_sealed")

    def __init__(self) -> None:
        self._roots: dict[str, _Node] | Mapping[str, _Node] = {
            kind: _Node() for kind in KINDS
        }
        self._entries: dict[tuple[str, str], Suggestion] | Mapping[
            tuple[str, str], Suggestion
        ] = {}
        self._normalized_labels: dict[tuple[str, str], str] | Mapping[
            tuple[str, str], str
        ] = {}
        self._node_count = len(KINDS)
        self._sealed = False

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def node_count(self) -> int:
        return self._node_count

    @property
    def sealed(self) -> bool:
        return self._sealed

    def insert(self, suggestion: Suggestion) -> None:
        """Insert or replace one `(kind, id)` entry, including rename updates."""
        self._ensure_mutable()
        normalized_label = normalize_label(suggestion.label)
        if len(normalized_label) > 1000:
            raise AutocompleteInputError("suggestion label exceeds 1000 normalized codepoints")
        key = suggestion_key(suggestion)
        previous = self._entries.get(key)
        if previous == suggestion:
            return
        if previous is not None:
            self._remove_entry(previous)
        self._normalized_labels[key] = normalized_label  # type: ignore[index]
        self._insert_entry(suggestion)
        self._entries[key] = suggestion  # type: ignore[index]

    def remove(self, kind: str, id: str) -> None:
        """Remove an exact source identity and prune/merge its old prefix path."""
        self._ensure_mutable()
        if kind not in KINDS or not isinstance(id, str) or not _ID_PATTERN.fullmatch(id):
            raise AutocompleteInputError("unknown suggestion kind")
        if int(id) > MAX_ID:
            raise AutocompleteInputError("suggestion id exceeds signed BIGINT")
        key = (kind, id)
        suggestion = self._entries.get(key)
        if suggestion is None:
            return
        self._remove_entry(suggestion)
        del self._entries[key]  # type: ignore[index]

    def search(
        self,
        prefix: str,
        limit: int = DEFAULT_RESULT_LIMIT,
        kinds: Sequence[str] | None = None,
    ) -> tuple[Suggestion, ...]:
        """Return the exact ordered top-K suggestions for a literal normalized prefix."""
        normalized = normalize_prefix(prefix)
        validate_limit(limit)
        selected_kinds = normalize_kinds(kinds)
        candidate_groups: list[tuple[_RankedCandidate, ...]] = []
        roots = self._roots
        for kind in selected_kinds:
            node = self._find_prefix_node(roots[kind], normalized)
            if node is not None:
                candidate_groups.append(node.candidates)
        if not candidate_groups:
            return ()
        ordered = merge(*candidate_groups, key=lambda candidate: candidate[:3])
        return tuple(candidate[3] for candidate in islice(ordered, limit))

    def seal(self) -> None:
        """Make the builder and all published trie maps read-only in place."""
        if self._sealed:
            return
        for root in self._roots.values():
            self._seal_node(root)
        self._roots = MappingProxyType(dict(self._roots))
        self._entries = MappingProxyType(dict(self._entries))
        self._normalized_labels = MappingProxyType(dict(self._normalized_labels))
        self._sealed = True

    def estimated_bytes(self) -> int:
        """Return an approximate retained Python object size, not process RSS."""
        seen: set[int] = set()
        total = 0
        proxy_overhead = sys.getsizeof(MappingProxyType({}))

        def add(value: object) -> None:
            nonlocal total
            identity = id(value)
            if identity not in seen:
                seen.add(identity)
                total += sys.getsizeof(value)

        add(self._roots)
        add(self._entries)
        add(self._normalized_labels)
        total += 3 * proxy_overhead  # sealed roots, identity map, and normalized-label map
        for key, suggestion in self._entries.items():
            add(key)
            add(key[0])
            add(key[1])
            add(suggestion)
            add(suggestion.id)
            add(suggestion.kind)
            add(suggestion.label)
            add(self._normalized_labels[key])
        stack = list(self._roots.values())
        while stack:
            node = stack.pop()
            add(node)
            add(node.edge)
            add(node.children)
            add(node.terminals)
            add(node.candidates)
            total += 2 * proxy_overhead  # sealed children and terminal maps
            for child_key, child in node.children.items():
                add(child_key)
                stack.append(child)
            for identity, suggestion in node.terminals.items():
                add(identity)
                add(suggestion)
            for suggestion in node.candidates:
                add(suggestion)
                add(suggestion[0])
                add(suggestion[1])
                add(suggestion[2])
                add(suggestion[3])
        return total

    def _ensure_mutable(self) -> None:
        if self._sealed:
            raise RuntimeError("a published autocomplete snapshot is immutable")

    def _refresh(self, node: _Node) -> None:
        candidates: dict[tuple[str, str], _RankedCandidate] = {}
        for identity, suggestion in node.terminals.items():
            candidates[identity] = (
                self._normalized_labels[identity],
                suggestion.kind,
                int(suggestion.id),
                suggestion,
            )
        for child in node.children.values():
            for candidate in child.candidates:
                candidates[(candidate[1], candidate[3].id)] = candidate
        node.candidates = tuple(
            sorted(candidates.values(), key=lambda candidate: candidate[:3])[:MAX_RESULT_LIMIT]
        )

    def _insert_entry(self, suggestion: Suggestion) -> None:
        normalized = normalize_label(suggestion.label)
        roots = self._roots
        root = roots[suggestion.kind]
        key = suggestion_key(suggestion)
        path = [root]
        offset = 0
        while offset < len(normalized):
            first = normalized[offset]
            child = root.children.get(first)
            if child is None:
                child = _Node(normalized[offset:])
                self._node_count += 1
                child.terminals = {key: suggestion}
                root.children[first] = child  # type: ignore[index]
                path.append(child)
                break

            remaining = normalized[offset:]
            common = _common_prefix_length(remaining, child.edge)
            if common == len(child.edge):
                offset += common
                root = child
                path.append(child)
                if offset == len(normalized):
                    child.terminals[key] = suggestion  # type: ignore[index]
                    break
                continue

            split = _Node(child.edge[:common])
            self._node_count += 1
            child.edge = child.edge[common:]
            split.children = {child.edge[0]: child}
            root.children[first] = split  # type: ignore[index]
            path.append(split)
            offset += common
            if offset == len(normalized):
                split.terminals = {key: suggestion}
            else:
                leaf = _Node(normalized[offset:])
                self._node_count += 1
                leaf.terminals = {key: suggestion}
                split.children[leaf.edge[0]] = leaf  # type: ignore[index]
                path.append(leaf)
            break

        for node in reversed(path):
            self._refresh(node)

    def _remove_entry(self, suggestion: Suggestion) -> None:
        normalized = normalize_label(suggestion.label)
        root = self._roots[suggestion.kind]
        path = [root]
        offset = 0
        while offset < len(normalized):
            child = root.children.get(normalized[offset])
            if child is None or not normalized[offset:].startswith(child.edge):
                return
            offset += len(child.edge)
            root = child
            path.append(child)
        key = suggestion_key(suggestion)
        if key not in root.terminals:
            return
        del root.terminals[key]  # type: ignore[index]

        for index in range(len(path) - 1, 0, -1):
            node = path[index]
            parent = path[index - 1]
            self._refresh(node)
            if not node.terminals and not node.children:
                del parent.children[node.edge[0]]  # type: ignore[index]
                self._node_count -= 1
            elif not node.terminals and len(node.children) == 1:
                child = next(iter(node.children.values()))
                node.edge += child.edge
                node.children = child.children
                node.terminals = child.terminals
                node.candidates = child.candidates
                self._node_count -= 1
            self._refresh(parent)
        self._refresh(path[0])
        del self._normalized_labels[key]  # type: ignore[index]

    @staticmethod
    def _find_prefix_node(root: _Node, prefix: str) -> _Node | None:
        offset = 0
        node = root
        while offset < len(prefix):
            child = node.children.get(prefix[offset])
            if child is None:
                return None
            remaining = prefix[offset:]
            common = _common_prefix_length(remaining, child.edge)
            if common == len(remaining):
                return child
            if common != len(child.edge):
                return None
            offset += common
            node = child
        return node

    @staticmethod
    def _seal_node(node: _Node) -> None:
        stack = [node]
        ordered: list[_Node] = []
        while stack:
            current = stack.pop()
            ordered.append(current)
            stack.extend(current.children.values())
        for current in reversed(ordered):
            current.children = MappingProxyType(dict(current.children))
            current.terminals = MappingProxyType(dict(current.terminals))


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


@dataclass(frozen=True, slots=True)
class IndexSnapshot:
    """A source-revision-tagged immutable trie snapshot."""

    generation: int
    trie: Trie
    _estimated_bytes: int = field(default=-1, repr=False)

    def __post_init__(self) -> None:
        if type(self.generation) is not int or not 1 <= self.generation <= 9_007_199_254_740_991:
            raise ValueError("snapshot generation must be a positive JSON-safe version")
        if self._estimated_bytes < 0:
            object.__setattr__(self, "_estimated_bytes", self.trie.estimated_bytes())
        self.trie.seal()

    @property
    def entries(self) -> int:
        return self.trie.entry_count

    @property
    def nodes(self) -> int:
        return self.trie.node_count

    @property
    def estimated_bytes(self) -> int:
        return self._estimated_bytes
