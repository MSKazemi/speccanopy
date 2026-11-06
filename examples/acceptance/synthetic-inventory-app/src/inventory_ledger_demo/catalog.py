"""Synthetic catalog records (acceptance-test fixture, not a real application)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    sku: str
    name: str


def sample_items() -> list[Item]:
    return [Item("DEMO-1", "Synthetic widget"), Item("DEMO-2", "Synthetic gadget")]
