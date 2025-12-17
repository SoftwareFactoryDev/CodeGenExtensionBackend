from pydantic import BaseModel
from typing import List, Optional

class Asset(BaseModel):
    name: str
    module: str
    signature: str
    description: str
    source_code: str

class Result(BaseModel):
    result: List[Asset]

class SearchRequest(BaseModel):
    topk: int
    requirement: str

class SearchResponse(BaseModel):
    result: List[Asset]

class ImportRepoRequest(BaseModel):
    repo_url: str

class ImportRepoResponse(BaseModel):
    message: str

class GenerateCodeRequest(BaseModel):
    example: List[Asset]
    requirement: str

class GenerateCodeResponse(BaseModel):
    code: str
    info: str

class GenerateCodeWithEditRequest(BaseModel):
    example: List[Asset]
    requirement: str

class GenerateCodeWithEditResponse(BaseModel):
    code: str
    info: str

class ReviewInfo(BaseModel):
    code: str
    type: str
    loc: int

class ReviewRequest(BaseModel):
    code: str

class ReviewResponse(BaseModel):
    result: str
    info: List[ReviewInfo]

class StoreRequest(BaseModel):
    name: str
    module: str
    code: str

class StoreResponse(BaseModel):
    message: str