"""Synthetic stock ledger (acceptance-test fixture, not a real application)."""

from inventory_ledger_demo.catalog import Item


class Ledger:
    def __init__(self) -> None:
        self._balance: dict[str, int] = {}

    def record(self, item: Item, delta: int) -> int:
        self._balance[item.sku] = self._balance.get(item.sku, 0) + delta
        return self._balance[item.sku]

    def balances(self) -> dict[str, int]:
        return dict(self._balance)
