from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy


class FakeGraphRuntime:
    """
    Fake configuravel para testes da fachada de aplicacao.

    Nao executa grafo real, SQL, rede ou adapters live.
    """

    def __init__(
        self,
        *,
        final_state: object = None,
        states: list[Mapping[str, object]] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.final_state = (
            deepcopy(dict(final_state))
            if isinstance(final_state, Mapping)
            else deepcopy(final_state)
        )
        self.states = [deepcopy(dict(item)) for item in (states or [])]
        self.exception = exception
        self.calls = 0
        self.initial_states: list[dict[str, object]] = []

    @property
    def last_initial_state(self) -> dict[str, object] | None:
        if not self.initial_states:
            return None
        return deepcopy(self.initial_states[-1])

    def invoke(
        self,
        initial_state: Mapping[str, object],
    ) -> object:
        self.calls += 1
        self.initial_states.append(deepcopy(dict(initial_state)))
        if self.exception is not None:
            raise self.exception
        if self.states:
            return deepcopy(self.states.pop(0))
        return deepcopy(self.final_state)
