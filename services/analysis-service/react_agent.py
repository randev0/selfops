"""
ReAct investigation agent (Reason + Act pattern).

Replaces the single-shot prompt with an iterative LangChain agent that:
  1. Reasons about what evidence to collect
  2. Calls tools (Prometheus, Loki, k8s API) to gather it
  3. Iterates until it has enough context
  4. Produces structured JSON + a full investigation_log of every step
"""

import json
import os
from typing import Any

import structlog
from langchain.agents import AgentExecutor, create_react_agent
from langchain.callbacks.base import BaseCallbackHandler
from langchain.prompts import PromptTemplate
from langchain.schema import AgentAction, AgentFinish
from langchain_openai import ChatOpenAI

from agent_tools import fetch_loki_logs, fetch_prometheus_metrics, get_k8s_resource_yaml
from schemas import AnalysisRequest, AnalysisResponse
from sop_retriever import get_retriever
import structured_output_parser

log = structlog.get_logger()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

TOOLS = [fetch_prometheus_metrics, fetch_loki_logs, get_k8s_resource_yaml]

# ReAct prompt — must expose exactly: {tools}, {tool_names}, {input}, {agent_scratchpad}
# Literal braces in the JSON example are escaped as {{ / }}
_REACT_PROMPT = PromptTemplate.from_template(
    "You are an expert Site Reliability Engineer conducting a live investigation "
    "of a Kubernetes infrastructure incident.\n"
    "Use the available tools to gather real evidence before concluding. "
    "Think step by step. Do not guess — look it up.\n\n"
    "TOOLS:\n{tools}\n\n"
    "FORMAT (follow exactly):\n"
    "Thought: what you need to investigate and why\n"
    "Action: one of [{tool_names}]\n"
    "Action Input: arguments for the tool\n"
    "Observation: tool result\n"
    "... (repeat Thought/Action/Action Input/Observation, max 6 iterations)\n"
    "Thought: I now have enough evidence to conclude\n"
    "Final Answer: a single JSON object — no markdown, no explanation — with "
    "exactly these keys:\n"
    '{{"summary": "2-3 sentence plain English description of what happened",'
    ' "probable_cause": "root cause based on evidence you gathered",'
    ' "evidence_points": ["specific finding 1", "specific finding 2", "specific finding 3"],'
    ' "recommended_action_id": "restart_deployment|rollout_restart|scale_up|null",'
    ' "confidence": 0.85,'
    ' "escalate": false,'
    ' "hypotheses": ['
    '   {{"title": "Primary hypothesis", "description": "full explanation grounded in evidence", "confidence": 0.85, "supporting_evidence": ["specific finding 1"]}},'
    '   {{"title": "Alternative hypothesis", "description": "less likely explanation", "confidence": 0.10, "supporting_evidence": []}}'
    ' ],'
    ' "evidence": ['
    '   {{"source": "prometheus|loki|k8s|alert", "kind": "metric|log|resource|alert", "label": "short_name", "value": "observed value"}}'
    ' ],'
    ' "action_plan": ['
    '   {{"action_id": "restart_deployment|rollout_restart|scale_up", "description": "why this action addresses the cause", "risk_level": "low|medium|high", "verification_steps": [{{"description": "what to check", "check": "metric_expression"}}]}}'
    ' ]'
    '}}\n\n'
    "Provide at least 2 hypotheses. "
    "If evidence is ambiguous (no single clear cause), provide 3 or more.\n\n"
    "INCIDENT:\n"
    "{input}\n\n"
    "Thought:{agent_scratchpad}"
)


class _ThoughtCaptureHandler(BaseCallbackHandler):
    """Collects every Thought / Action / Observation / Finish step."""

    def __init__(self) -> None:
        self.steps: list[dict] = []

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> None:
        # action.log contains "Thought: ...\nAction: ...\nAction Input: ..."
        thought_text = action.log or ""
        # Trim to just the Thought part
        if "\nAction:" in thought_text:
            thought_text = thought_text[: thought_text.index("\nAction:")]
        thought_text = thought_text.replace("Thought:", "").strip()

        if thought_text:
            self.steps.append({"type": "thought", "content": thought_text})

        self.steps.append(
            {
                "type": "action",
                "tool": action.tool,
                "input": str(action.tool_input)[:400],
            }
        )

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        self.steps.append(
            {"type": "observation", "content": str(output)[:600]}
        )

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        # Record the raw final answer for debugging
        self.steps.append(
            {"type": "conclusion", "content": str(finish.log)[:300]}
        )


def _parse_json_from_text(text: str) -> dict:
    """Extract the first valid JSON object from the agent's output text."""
    text = text.strip()
    # Strip accidental markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    log.warning("Could not parse JSON from agent output", preview=text[:200])
    return {
        "summary": text[:400] if text else "Agent produced no output",
        "probable_cause": "Could not parse structured output — see investigation_log",
        "evidence_points": [],
        "recommended_action_id": None,
        "confidence": 0.2,
        "escalate": True,
    }


async def run_investigation(request: AnalysisRequest) -> AnalysisResponse:
    """Run the ReAct agent and return a structured AnalysisResponse."""

    if not OPENROUTER_API_KEY:
        log.warning("OPENROUTER_API_KEY not set")
        return AnalysisResponse(
            summary="Analysis skipped — OpenRouter API key not configured.",
            probable_cause="Unknown — manual investigation required.",
            evidence_points=["API key missing"],
            recommended_action_id=None,
            confidence=0.0,
            escalate=True,
            raw_output={},
            investigation_log=[{"type": "error", "content": "OPENROUTER_API_KEY not set"}],
        )

    llm = ChatOpenAI(
        model="anthropic/claude-3-haiku",
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/selfops",
            "X-Title": "SelfOps",
        },
        temperature=0.1,
        max_tokens=2048,
    )

    agent = create_react_agent(llm, TOOLS, _REACT_PROMPT)
    capture = _ThoughtCaptureHandler()

    executor = AgentExecutor(
        agent=agent,
        tools=TOOLS,
        callbacks=[capture],
        max_iterations=6,
        handle_parsing_errors="Agent produced unexpected output — continue investigating.",
        verbose=False,
    )

    allowed_str = ", ".join(
        f"{a['action_id']} ({a['name']})" for a in request.allowed_actions
    )

    # Retrieve relevant company SOPs for this incident
    sop_query = (
        f"{request.incident_title} {request.alert_name} "
        f"{request.service_name or ''} {request.namespace or ''}"
    )
    sop_context = get_retriever().format_for_prompt(sop_query)

    # Log SOP context into investigation steps for audit trail
    if sop_context:
        capture.steps.append({
            "type": "sop_context",
            "content": sop_context.strip(),
        })

    incident_context = (
        f"Title: {request.incident_title}\n"
        f"Service: {request.service_name or 'unknown'} | "
        f"Namespace: {request.namespace or 'platform'}\n"
        f"Alert: {request.alert_name}\n"
        f"Labels: {json.dumps(request.alert_labels)}\n"
        f"Annotations: {json.dumps(request.alert_annotations)}\n"
        f"Available remediation actions: {allowed_str}\n"
        f"{sop_context}"
        f"\nStart by querying Prometheus for relevant metrics, "
        f"then check Loki for error logs, "
        f"then fetch the Kubernetes resource state if needed. "
        f"If SOPs are provided above, your recommendation MUST cite them."
    )

    try:
        result = await executor.ainvoke({"input": incident_context})
        raw_text = result.get("output", "")
        log.info("ReAct agent finished", steps=len(capture.steps), output_len=len(raw_text))
        parsed = _parse_json_from_text(raw_text)

    except Exception as exc:
        log.error("ReAct agent execution failed", error=str(exc))
        capture.steps.append({"type": "error", "content": str(exc)})
        return AnalysisResponse(
            summary="Investigation failed during agent execution.",
            probable_cause="Unknown — manual investigation required.",
            evidence_points=["Agent execution raised an exception — see investigation_log"],
            recommended_action_id=None,
            confidence=0.0,
            escalate=True,
            raw_output={"error": str(exc)},
            investigation_log=capture.steps,
        )

    structured = structured_output_parser.parse(parsed)

    return AnalysisResponse(
        summary=parsed.get("summary", "No summary produced"),
        probable_cause=parsed.get("probable_cause", "Unknown"),
        evidence_points=parsed.get("evidence_points", []),
        recommended_action_id=parsed.get("recommended_action_id"),
        confidence=float(parsed.get("confidence", 0.0)),
        escalate=bool(parsed.get("escalate", True)),
        raw_output=parsed,
        investigation_log=capture.steps,
        structured=structured,
    )
