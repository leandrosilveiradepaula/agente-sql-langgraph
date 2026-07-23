from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict, total=False):
    """
    Estado compartilhado entre os nodes do grafo.

    total=False permite iniciar o grafo apenas com alguns campos,
    como a pergunta original.
    """

    question: str
    normalized_question: str
    current_stage: str
    final_status: str


def receive_question(state: GraphState) -> GraphState:
    """
    Primeiro node do grafo.

    Recebe a pergunta e faz apenas uma normalização textual básica.
    Ainda não existe interpretação financeira nem chamada de IA.
    """

    print("1. Node receive_question executado")

    question = state.get("question", "").strip()
    normalized_question = " ".join(question.split())

    return {
        "question": question,
        "normalized_question": normalized_question,
        "current_stage": "receive_question",
        "final_status": "processing",
    }


def finalize(state: GraphState) -> GraphState:
    """
    Último node do grafo.

    Apenas marca a execução como concluída.
    """

    print("2. Node finalize executado")

    return {
        "current_stage": "finalize",
        "final_status": "completed",
    }


def create_graph():
    """
    Monta e compila o grafo.
    """

    builder = StateGraph(GraphState)

    builder.add_node("receive_question", receive_question)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "receive_question")
    builder.add_edge("receive_question", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


if __name__ == "__main__":
    graph = create_graph()

    initial_state: GraphState = {
        "question": (
            "Quais as contas que tiveram maiores "
            "estouros de orçamento no mês?"
        )
    }

    result = graph.invoke(initial_state)

    print("\nResultado final do grafo:")

    for key, value in result.items():
        print(f"{key}: {value}")