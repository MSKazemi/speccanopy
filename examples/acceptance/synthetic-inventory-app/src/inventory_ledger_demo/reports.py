"""Synthetic balance report (acceptance-test fixture, not a real application)."""

from inventory_ledger_demo import catalog
from .ledger import Ledger


def summarize(ledger: Ledger) -> list[str]:
    names = {item.sku: item.name for item in catalog.sample_items()}
    return [f"{names.get(sku, sku)}: {qty}" for sku, qty in sorted(ledger.balances().items())]
