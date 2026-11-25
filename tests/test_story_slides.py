"""Validation tests for the three cinematic story slide types: ledger_layers, tx_journey, mesh_network."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402


def _base_deck(slide: dict) -> dict:
    return {
        "slug": "story-test",
        "brand": "DUP LABS",
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "voice": {"engine": "edge_tts", "lang": "ru", "speaker": "dmitry", "rate": "95%"},
        "slides": [slide],
    }


def _valid_ledger_layers() -> dict:
    return {
        "id": "s_layers",
        "tag": "СЛОИ",
        "type": "ledger_layers",
        "title": "Пять слоёв книги",
        "voice_text": "Книга разделена на слои.",
        "layers": [
            {"id": "l1", "name": "API", "tech": "REST", "desc": "Вход", "guarantee": "Проверка границ"},
            {"id": "l2", "name": "Оркестрация", "tech": "Python", "desc": "Политика", "guarantee": "Консенсус"},
            {"id": "l3", "name": "Хранение", "tech": "RocksDB", "desc": "Запись", "guarantee": "Атомарность"},
        ],
    }


def _valid_tx_journey() -> dict:
    return {
        "id": "s_tx",
        "tag": "ТРАНЗАКЦИЯ",
        "type": "tx_journey",
        "title": "Путь транзакции",
        "voice_text": "Транзакция проходит цепочку.",
        "journey": {
            "tx_label": "TX #7a9f",
            "amount_label": "100 000 sat",
            "signature_label": "ECDSA ✓",
            "merkle_leaves": ["tx·a1", "tx·b2", "tx·c3", "TX*"],
            "blocks": [
                {"height": "#49344", "hash": "0x445ec...", "tx_count": "12 tx"},
                {"height": "#49345", "hash": "0x5465a...", "tx_count": "18 tx"},
                {"height": "#49346", "hash": "0x9fd8a...", "tx_count": "14 tx", "sealed": True},
            ],
            "steps": [
                {"title": "Подпись", "badge": "ECDSA", "detail": "Проверка ключа"},
                {"title": "Мемпул", "badge": "RUST", "detail": "Фильтр спама"},
                {"title": "Блок", "badge": "MERKLE", "detail": "Корень состояния"},
            ],
        },
    }


def _valid_mesh_network() -> dict:
    return {
        "id": "s_mesh",
        "tag": "СЕТЬ",
        "type": "mesh_network",
        "title": "Три узла",
        "voice_text": "Три узла держат сеть.",
        "mesh": {
            "protocol_label": "rust-libp2p Noise",
            "chain_id": "778888",
            "probe_label": "wire_probe_ok · aligned",
            "nodes": [
                {"id": "node1", "role": "Leader", "endpoint": ":18180", "status": "ALIGNED"},
                {"id": "node2", "role": "Peer", "endpoint": ":18181", "status": "ALIGNED"},
                {"id": "node3", "role": "Peer", "endpoint": ":18182", "status": "ALIGNED"},
            ],
            "recovery_steps": [
                {"title": "CatchUp", "desc": "Догон высоты"},
                {"title": "Fail-Closed", "desc": "Честный отказ"},
            ],
        },
    }


class StorySlideValidationTests(unittest.TestCase):
    def test_valid_story_slides_pass(self) -> None:
        for slide in (_valid_ledger_layers(), _valid_tx_journey(), _valid_mesh_network()):
            build_deck.validate_deck(_base_deck(slide), check_assets=False)

    def test_ledger_layers_refuses_too_few_or_duplicate_ids(self) -> None:
        s = _valid_ledger_layers()
        s["layers"] = s["layers"][:2]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s), check_assets=False)

        s2 = _valid_ledger_layers()
        s2["layers"][1]["id"] = s2["layers"][0]["id"]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s2), check_assets=False)

        s3 = _valid_ledger_layers()
        s3["layers"][0]["guarantee"] = "   "
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s3), check_assets=False)

    def test_tx_journey_refuses_missing_blocks_steps_or_bad_leaves(self) -> None:
        s = _valid_tx_journey()
        s["journey"]["blocks"] = s["journey"]["blocks"][:2]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s), check_assets=False)

        s2 = _valid_tx_journey()
        s2["journey"]["steps"] = s2["journey"]["steps"][:2]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s2), check_assets=False)

        s3 = _valid_tx_journey()
        s3["journey"]["merkle_leaves"] = ["only_one"]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s3), check_assets=False)

    def test_mesh_network_refuses_under_three_nodes_or_bad_recovery(self) -> None:
        s = _valid_mesh_network()
        s["mesh"]["nodes"] = s["mesh"]["nodes"][:2]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s), check_assets=False)

        s2 = copy.deepcopy(_valid_mesh_network())
        s2["mesh"]["nodes"][1]["id"] = "node1"
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s2), check_assets=False)

        s3 = copy.deepcopy(_valid_mesh_network())
        s3["mesh"]["recovery_steps"] = [{"title": "Only one", "desc": "Too short"}]
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(_base_deck(s3), check_assets=False)


if __name__ == "__main__":
    unittest.main()
