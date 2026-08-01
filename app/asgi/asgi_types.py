from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, TypedDict


ASGI_ADAPTER_CONTRACT_VERSION = "v1.0.0-asgi-entry-adapter"

AsgiScopeType = Literal["http", "lifespan", "websocket"]


class AsgiAdapterLimits(TypedDict):
    max_request_body_bytes: int
    max_request_chunks: int
    max_header_count: int
    max_header_name_bytes: int
    max_header_value_bytes: int
    max_path_bytes: int
    max_query_string_bytes: int
    max_method_bytes: int
    max_scheme_bytes: int
    max_client_host_bytes: int
    max_server_host_bytes: int
    max_response_headers: int
    max_response_header_name_bytes: int
    max_response_header_value_bytes: int


class AsgiError(Exception):
    def __init__(self, code: str, *, status_code: int = 400) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


AsgiScope = Mapping[str, Any]
AsgiMessage = dict[str, Any]
AsgiReceive = Callable[[], Awaitable[AsgiMessage]]
AsgiSend = Callable[[AsgiMessage], Awaitable[None]]


class HeaderPairs(Mapping[str, str]):
    def __init__(self, pairs: tuple[tuple[str, str], ...]) -> None:
        self._pairs = tuple((str(name), str(value)) for name, value in pairs)

    def __iter__(self):
        seen: set[str] = set()
        for name, _value in self._pairs:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                yield name

    def __len__(self) -> int:
        return len(self._pairs)

    def __getitem__(self, key: str) -> str:
        for name, value in self._pairs:
            if name.casefold() == str(key).casefold():
                return value
        raise KeyError(key)

    def items(self):  # type: ignore[override]
        return iter(self._pairs)

    def keys(self):  # type: ignore[override]
        return (name for name, _value in self._pairs)

    def values(self):  # type: ignore[override]
        return (value for _name, value in self._pairs)

    def get(self, key: object, default: object = None) -> object:
        if not isinstance(key, str):
            return default
        try:
            return self[key]
        except KeyError:
            return default

    def __repr__(self) -> str:
        return "HeaderPairs(<redacted>)"
