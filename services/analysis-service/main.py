from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from schemas import AnalysisRequest, AnalysisResponse
from prompt_builder import build_prompt
from llm_client import call_llm

log = structlog.get_logger()

app = FastAPI(
    title="SelfOps Analysis Service",
    description="LLM-powered incident analysis via OpenRouter",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "selfops-analysis"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    log.info("analyze request received", incident_id=request.incident_id)

    prompt = build_prompt(request)
    result = await call_llm(prompt)

    if "error" in result:
        log.warning("LLM error, returning fallback", error=result.get("error"))
        return AnalysisResponse(
            summary="Analysis failed - raw LLM output stored for review",
            probable_cause="Unknown - manual investigation required",
            evidence_points=["LLM call failed or returned unparseable output"],
            recommended_action_id=None,
            confidence=0.0,
            escalate=True,
            raw_output=result,
        )

    return AnalysisResponse(
        summary=result.get("summary", "No summary available"),
        probable_cause=result.get("probable_cause", "Unknown"),
        evidence_points=result.get("evidence_points", []),
        recommended_action_id=result.get("recommended_action_id"),
        confidence=float(result.get("confidence", 0.0)),
        escalate=bool(result.get("escalate", False)),
        raw_output=result,
    )
