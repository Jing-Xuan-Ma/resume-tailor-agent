"""
LangGraph Agent Definition for Resume Tailoring.

This defines the state machine that orchestrates:
  understand -> retrieve_memory -> parse_jd -> match_experiences -> tailor -> guard -> respond
"""

from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END

# We'll define a simple dict-based state for now.
# In production, you'd use a stricter TypedDict.

class TailorState(TypedDict, total=False):
    user_id: str
    resume_id: str
    user_input: str
    resume_data: dict
    jd_text: str
    jd_parsed: dict | None
    matched_experiences: list | None
    tailored_resume: dict | None
    evidence_check: dict | None
    agent_response: str
    requires_clarification: bool
    memory_context: dict


# =============================================================================
# Nodes (simplified stubs — to be expanded)
# =============================================================================

async def understand_intent_node(state: TailorState) -> TailorState:
    """Classify user intent: upload resume, paste JD, or general chat."""
    # TODO: Implement intent classification via LLM
    return {**state, "agent_response": "Understood. Let me analyze the job description."}


async def retrieve_memory_node(state: TailorState) -> TailorState:
    """Retrieve relevant experiences and conversation history from memory."""
    # TODO: Integrate with long_term.py vector store
    return {**state, "memory_context": {"experiences": [], "chat_history": []}}


async def parse_jd_node(state: TailorState) -> TailorState:
    """Parse raw JD text into structured fields."""
    from app.modules.resume_tailor.nodes.parse_jd import JDParsingNode
    parser = JDParsingNode()
    parsed = await parser.parse(state["jd_text"])
    return {**state, "jd_parsed": parsed.model_dump()}


async def match_experiences_node(state: TailorState) -> TailorState:
    """Find the user's most relevant experiences for this JD."""
    # TODO: Vector similarity search against user experiences
    return {**state, "matched_experiences": []}


async def tailor_resume_node(state: TailorState) -> TailorState:
    """Generate the tailored resume using LLM."""
    from app.modules.resume_tailor.nodes.tailor_resume import TailorResumeNode
    tailor = TailorResumeNode()
    tailored = await tailor.run(
        resume_data=state.get("resume_data", {}),
        jd_parsed=state.get("jd_parsed", {}),
        matched_experiences=state.get("matched_experiences", []),
        memory_context=state.get("memory_context", {}),
    )
    return {**state, "tailored_resume": tailored}


async def evidence_guard_node(state: TailorState) -> TailorState:
    """Verify that tailored claims are supported by original experiences."""
    from app.modules.resume_tailor.nodes.evidence_guard import EvidenceGuardNode
    guard = EvidenceGuardNode()
    check = await guard.verify(
        original_resume=state.get("resume_data", {}),
        tailored_resume=state.get("tailored_resume", {}),
    )
    return {
        **state,
        "evidence_check": check,
        "requires_clarification": not check.get("passed", False),
    }


async def generate_response_node(state: TailorState) -> TailorState:
    """Generate the final user-facing response."""
    if state.get("requires_clarification"):
        response = (
            "I need a bit more clarity to ensure accuracy.\n\n"
            f"{state.get('evidence_check', {}).get('issues', ['Please provide more details.'])[0]}"
        )
    else:
        response = (
            "I've tailored your resume for this role! Here's a summary of changes:\n\n"
            f"{state.get('tailored_resume', {}).get('tailoring_summary', 'Resume updated.')}\n\n"
            "You can review the full tailored resume in the preview panel."
        )
    return {**state, "agent_response": response}


# =============================================================================
# Build the Graph
# =============================================================================

workflow = StateGraph(TailorState)

workflow.add_node("understand", understand_intent_node)
workflow.add_node("retrieve_memory", retrieve_memory_node)
workflow.add_node("parse_jd", parse_jd_node)
workflow.add_node("match_experiences", match_experiences_node)
workflow.add_node("tailor", tailor_resume_node)
workflow.add_node("guard", evidence_guard_node)
workflow.add_node("respond", generate_response_node)

# Linear flow with conditional edge from guard
workflow.set_entry_point("understand")
workflow.add_edge("understand", "retrieve_memory")
workflow.add_edge("retrieve_memory", "parse_jd")
workflow.add_edge("parse_jd", "match_experiences")
workflow.add_edge("match_experiences", "tailor")
workflow.add_edge("tailor", "guard")


def guard_router(state: TailorState) -> str:
    if state.get("requires_clarification"):
        return "respond"
    return "respond"


workflow.add_conditional_edges(
    "guard",
    guard_router,
    {"respond": "respond"}
)

workflow.add_edge("respond", END)

# Compile the agent
tailor_agent = workflow.compile()
