"""Results for a fair multi-asset comparison."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from backend.app.models.dca import DCAResult


@dataclass(frozen=True, slots=True)
class DCAComparisonResult(Sequence[DCAResult]):
    """Ranked results plus assets that could not supply usable history."""

    results: tuple[DCAResult, ...]
    unavailable_symbols: tuple[str, ...] = ()

    def __getitem__(self, index):  # type: ignore[no-untyped-def]
        return self.results[index]

    def __len__(self) -> int:
        return len(self.results)

    def __iter__(self) -> Iterator[DCAResult]:
        return iter(self.results)


