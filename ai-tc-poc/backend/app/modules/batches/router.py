from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.modules.batches.repository import BatchRepository, BatchRuleError
from app.schemas.batches import BatchApprovalRequest, BatchApprovalResponse, CreateExecutionSuiteRequest, CreateStructureBatchRequest, ExecutionSuiteResponse, StructureBatchResponse

router = APIRouter(tags=["batches"])

def repository(session, request):
    settings=get_settings()
    return BatchRepository(session,settings,UUID(settings.default_user_id),UUID(request.state.request_id))

def translate(exc):
    code=404 if exc.code.endswith("NOT_FOUND") else 409 if "CONFLICT" in exc.code else 422
    return DomainError(exc.code,exc.message,code,retryable=False)

@router.post("/test-case-structure-batches",response_model=StructureBatchResponse,status_code=status.HTTP_202_ACCEPTED)
async def create_structure_batch(body:CreateStructureBatchRequest,request:Request,idempotency_key:str|None=Header(default=None),session:AsyncSession=Depends(get_session)):
    if not idempotency_key: raise DomainError("IDEMPOTENCY_KEY_REQUIRED","Idempotency-Key 헤더가 필요합니다.")
    if body.maxAiCallsPerCase != 0: raise DomainError("AI_CALLS_DISABLED","현재 Batch 구조화의 maxAiCallsPerCase는 0이어야 합니다.",422)
    try: return await repository(session,request).create_structure_batch(body,idempotency_key)
    except BatchRuleError as exc: raise translate(exc) from None

@router.get("/test-case-structure-batches/{batch_id}",response_model=StructureBatchResponse)
async def get_structure_batch(batch_id:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    try: return await repository(session,request).structure_batch(batch_id)
    except BatchRuleError as exc: raise translate(exc) from None

@router.post("/test-case-structure-batches/{batch_id}/approve",response_model=BatchApprovalResponse)
async def approve_structure_batch(batch_id:UUID,body:BatchApprovalRequest,request:Request,session:AsyncSession=Depends(get_session)):
    try: return await repository(session,request).approve(batch_id,body)
    except BatchRuleError as exc: raise translate(exc) from None

@router.post("/execution-suites",response_model=ExecutionSuiteResponse,status_code=status.HTTP_202_ACCEPTED)
async def create_execution_suite(body:CreateExecutionSuiteRequest,request:Request,idempotency_key:str|None=Header(default=None),session:AsyncSession=Depends(get_session)):
    if not idempotency_key: raise DomainError("IDEMPOTENCY_KEY_REQUIRED","Idempotency-Key 헤더가 필요합니다.")
    if body.limits.maxAiCalls != 0: raise DomainError("AI_CALLS_DISABLED","Suite 실행의 maxAiCalls는 0이어야 합니다.",422)
    try: return await repository(session,request).create_suite(body,idempotency_key)
    except BatchRuleError as exc: raise translate(exc) from None

@router.get("/execution-suites/{suite_id}",response_model=ExecutionSuiteResponse)
async def get_execution_suite(suite_id:UUID,request:Request,session:AsyncSession=Depends(get_session)):
    try: return await repository(session,request).suite(suite_id)
    except BatchRuleError as exc: raise translate(exc) from None
