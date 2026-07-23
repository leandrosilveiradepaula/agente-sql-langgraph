from typing import Protocol

from app.domain.context import ContextSnapshot


class ContextRepositoryError(RuntimeError):
    """
    Erro conhecido ao carregar o contexto.
    """


class ContextRepository(Protocol):
    """
    Contrato para qualquer fonte de contexto.

    Futuramente haverá uma implementação Supabase/Postgres.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        """
        Carrega o contexto ativo para o perfil informado.
        """
        ...