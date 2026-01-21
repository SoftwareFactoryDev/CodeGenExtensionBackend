from pydantic import BaseModel
from typing import List, Optional


class ImportRepoRequest(BaseModel):
    repo_url: str


class ImportRepoResponse(BaseModel):
    message: str


class Asset(BaseModel):
    name: str
    module: str
    signature: str
    description: str
    source_code: str


class SearchRequest(BaseModel):
    keywords: str


class SearchResponse(BaseModel):
    result: List[Asset]


class SearchCodeRequest(BaseModel):
    code: str


class SearchCodeResponse(BaseModel):
    result: List[Asset]


class TempAsset(BaseModel):
    id: str
    name: str
    module: str
    signature: str
    description: str
    source_code: str


class ImAssetRequest(BaseModel):
    lib: str
    assets: List[str]


class ImAssetResponse(BaseModel):
    message: str
    assets: List[TempAsset]


class TempAssetRequest(BaseModel):
    lib: str


class TempAssetResponse(BaseModel):
    assets: List[TempAsset]


class RmTempAssetRequest(BaseModel):
    lib: str
    asset: str


class RmTempAssetResponse(BaseModel):
    message: str


class EditAssetRequest(BaseModel):
    lib: str
    asset: TempAsset


class EditAssetResponse(BaseModel):
    message: str
    assets: List[TempAsset]


class LibRegsResponse(BaseModel):
    id: str


class RequirementItem(BaseModel):
    id: str
    content: str


class ImReqResponse(BaseModel):
    requirements: List[RequirementItem]


class Result(BaseModel):
    result: List[Asset]


class GenerateCodeRagRequest(BaseModel):
    requirements: List[RequirementItem]


class CodeGenResult(BaseModel):
    id: str
    content: str
    code: str
    assets: List[Asset]
    info: str


class GenerateCodeRagResponse(BaseModel):
    result: List[CodeGenResult]


class EditCodeRequest(BaseModel):
    id: str
    content: str
    edit: str
    code: str
    assets: List[Asset]


class EditCodeResponse(BaseModel):
    code: str
    info: str


class StoreAsset(BaseModel):
    name: str
    module: str
    code: str


class StoreRequest(BaseModel):
    lib: str
    assets: List[StoreAsset]


class StoreResponse(BaseModel):
    message: str
    assets: List[TempAsset]


class ErrorInfo(BaseModel):
    desp: str
    line: int
    col: int


class ReviewRequest(BaseModel):
    code: str


class ReviewResponse(BaseModel):
    type: str
    err: List[ErrorInfo]


class FixInfo(BaseModel):
    code: str
    type: str
    loc: int


class FixRequest(BaseModel):
    code: str
    type: str
    err: List[ErrorInfo]


class FixResponse(BaseModel):
    type: str
    err: List[ErrorInfo]
    result: str
    info: List[FixInfo]
class ConfigRequest(BaseModel):
    info: str