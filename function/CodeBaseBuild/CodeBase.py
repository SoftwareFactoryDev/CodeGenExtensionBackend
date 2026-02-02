import os
import json
from copy import deepcopy
from typing import List, Dict, Any, Optional, Callable, Union

import jieba
from filelock import FileLock
import chromadb
from chromadb.config import Settings

from app.logger import logger_global

class CodeBase:
    """
    代码资产库类
    """
    
    def __init__(
        self,
        library_id: str,
        persist_directory: str = "./codebase",
        embedding_func: Optional[Callable] = None,
        update_module_desc_hook: Optional[Callable] = None,
        update_system_desc_hook: Optional[Callable] = None
    ):
        """
        初始化资产库
        
        Args:
            library_id: 资产库唯一标识
            persist_directory: 持久化根目录
            embedding_func: 自定义embedding函数（接受List[str]返回List[List[float]]）
            update_module_desc_hook: 模块description更新钩子 (module_id, old_desc, change_info) -> new_desc
            update_system_desc_hook: 系统description更新钩子 (system_id, old_desc, change_info) -> new_desc
        """

        # 加载代码库信息
        self.library_id = library_id
        self.base_dir = os.path.abspath(persist_directory)
        self.library_dir = os.path.join(self.base_dir, library_id)
        self.logger = deepcopy(logger_global)
        self.logger.info(f'初始化资产库：{self.library_id}, 路径：{self.library_dir}')
        os.makedirs(self.library_dir, exist_ok=True)
        
        # 添加文件锁
        self.lock_path = os.path.join(self.library_dir, ".asset_library.lock")
        self.lock = FileLock(self.lock_path, timeout=10)
        self.logger.info(f'已添加文件锁')
        
        # 初始化Embedding
        self.embedding_func = embedding_func
        self.logger.info("使用自定义Embedding函数")
        
        # 初始化ChromaDB
        self.client = chromadb.PersistentClient(
            path=self.library_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        self.logger.info("初始化ChromaDB成功")
        
        # 创建/获取三个Collection
        self.system_coll = self.client.get_or_create_collection(
            name="system_assets",
            embedding_function=self.embedding_func,
            metadata={"hnsw:space": "cosine"}  # 余弦相似度
        )
        self.module_coll = self.client.get_or_create_collection(
            name="module_assets",
            embedding_function=self.embedding_func,
            metadata={"hnsw:space": "cosine"}
        )
        self.element_coll = self.client.get_or_create_collection(
            name="element_assets",
            embedding_function=self.embedding_func,
            metadata={"hnsw:space": "cosine"}
        )
        
        # 更新钩子
        self.update_module_hook = update_module_desc_hook
        self.update_system_hook = update_system_desc_hook
        
        self.logger.info(f"资产库初始化成功: {library_id} | 路径: {self.library_dir}")
        self._log_stats()
    
    # ==================== 数据存储接口 ====================
    
    def add_system_asset(self, asset: Dict[str, Any]) -> bool:
        """添加/更新系统级资产"""
        required = {"id", "name", "version", "description"}
        if not required.issubset(asset.keys()):
            raise ValueError(f"系统资产缺少必要字段: {required - asset.keys()}")
        
        with self.lock:
            try:
                self.system_coll.add(
                    ids=[asset["id"]],
                    documents=[asset["description"]],
                    metadatas=[asset]
                )
                self.logger.info(f"系统资产添加成功: {asset['id']}")
                return True
            except Exception as e:
                self.logger.error(f"系统资产添加失败 {asset['id']}: {str(e)}")
                return False
    
    def add_module_asset(self, asset: Dict[str, Any]) -> bool:
        """添加/更新模块级资产"""
        required = {"id", "name", "description", "path", "repo"}
        if not required.issubset(asset.keys()):
            raise ValueError(f"模块资产缺少必要字段: {required - asset.keys()}")
        
        with self.lock:
            try:
                self.module_coll.add(
                    ids=[asset["id"]],
                    documents=[asset["description"]],
                    metadatas=[asset]
                )
                self.logger.info(f"模块资产添加成功: {asset['id']}")
                return True
            except Exception as e:
                self.logger.error(f"模块资产添加失败 {asset['id']}: {str(e)}")
                return False
    
    def add_element_asset(self, asset: Dict[str, Any]) -> bool:
        """
        添加/更新要素级资产（自动处理中文分词用于BM25）
        支持函数/数据结构/全局变量/宏定义四种子类型
        """
        required = {"id", "description", "source_code", "module", "repo"}
        if not required.issubset(asset.keys()):
            raise ValueError(f"要素资产缺少必要字段: {required - asset.keys()}")
        
        # 为BM25检索预处理：添加分词后的文档（ChromaDB 0.4.22+ 支持）
        tokenized_desc = " ".join(list(jieba.cut_for_search(asset["description"])))
        
        with self.lock:
            try:
                self.element_coll.add(
                    ids=[asset["id"]],
                    documents=[asset["description"]],  # 向量检索用
                    metadatas=[{
                        **asset,
                        "_tokenized_desc": tokenized_desc  # BM25检索关键字段
                    }]
                )
                self.logger.info(f"要素资产添加成功: {asset['id']} | 类型: {asset.get('type', 'function')}")
                return True
            except Exception as e:
                self.logger.error(f"要素资产添加失败 {asset['id']}: {str(e)}")
                return False
    
    # ==================== 数据删除（含级联逻辑） ====================
    
    def delete_element_asset(self, element_id: str) -> bool:
        """删除要素资产，并级联更新/删除父级资产"""
        with self.lock:
            try:
                # 1. 获取要素信息（删除前）
                result = self.element_coll.get(ids=[element_id], include=["metadatas"])
                if not result["ids"]:
                    self.logger.warning(f"要素资产不存在: {element_id}")
                    return False
                
                meta = result["metadatas"][0]
                module_id = meta["module"]
                repo_id = meta["repo"]
                
                # 2. 删除要素
                self.element_coll.delete(ids=[element_id])
                self.logger.info(f"要素资产已删除: {element_id}")
                
                # 3. 检查模块是否还有子要素
                module_elements = self.element_coll.get(
                    where={"module": module_id},
                    include=[]
                )
                module_has_children = len(module_elements["ids"]) > 0
                
                # 4. 更新模块description（通过钩子）
                if not module_has_children:
                    # 模块无子要素，删除模块
                    self.module_coll.delete(ids=[module_id])
                    self.logger.info(f"级联删除空模块: {module_id}")
                elif self.update_module_hook:
                    # 有钩子则调用更新
                    old_module = self.module_coll.get(ids=[module_id], include=["metadatas"])["metadatas"][0]
                    new_desc = self.update_module_hook(
                        module_id, 
                        old_module["description"],
                        {"deleted_element": element_id, "remaining_count": len(module_elements["ids"])}
                    )
                    if new_desc and new_desc != old_module["description"]:
                        old_module["description"] = new_desc
                        self.module_coll.update(ids=[module_id], documents=[new_desc], metadatas=[old_module])
                        self.logger.info(f"模块description已更新: {module_id}")
                
                # 5. 检查系统是否还有子模块/要素
                system_modules = self.module_coll.get(where={"repo": repo_id}, include=[])
                system_elements = self.element_coll.get(where={"repo": repo_id}, include=[])
                system_has_children = len(system_modules["ids"]) > 0 or len(system_elements["ids"]) > 0
                
                if not system_has_children:
                    self.system_coll.delete(ids=[repo_id])
                    self.logger.info(f"级联删除空系统: {repo_id}")
                elif self.update_system_hook:
                    old_system = self.system_coll.get(ids=[repo_id], include=["metadatas"])["metadatas"][0]
                    new_desc = self.update_system_hook(
                        repo_id,
                        old_system["description"],
                        {"deleted_element": element_id, "modules_remaining": len(system_modules["ids"])}
                    )
                    if new_desc and new_desc != old_system["description"]:
                        old_system["description"] = new_desc
                        self.system_coll.update(ids=[repo_id], documents=[new_desc], metadatas=[old_system])
                        self.logger.info(f"系统description已更新: {repo_id}")
                
                return True
            except Exception as e:
                self.logger.error(f"删除要素资产失败 {element_id}: {str(e)}")
                return False
    
    # ==================== 智能检索核心 ====================
    
    def _prepare_query(self, query: Union[str, List[str]]) -> str:
        """统一查询输入格式"""
        if isinstance(query, list):
            return " ".join(query)
        return query.strip()
    
    def search_system_assets(
        self, 
        query: Union[str, List[str]], 
        ratio: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        系统级资产检索：基于description的向量相似度
        Args:
            query: 查询文本/关键词列表
            ratio: 返回结果占总数比例（最小1个）
        """
        query_text = self._prepare_query(query)
        total = self.system_coll.count()
        n_results = max(1, int(total * ratio))
        
        results = self.system_coll.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["metadatas", "distances"]
        )
        
        return self._format_results(results, total)
    
    def search_module_assets(
        self,
        query: Union[str, List[str]],
        repo_scope: Optional[List[str]] = None,
        ratio: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        模块级资产检索：支持系统范围过滤 + 向量检索
        """
        query_text = self._prepare_query(query)
        # 构建过滤条件
        where = {"repo": {"$in": repo_scope}} if repo_scope else None
        
        total = self.module_coll.count()
        n_results = max(1, int(total * ratio))
        
        results = self.module_coll.query(
            query_texts=[query_text],
            where=where,
            n_results=n_results,
            include=["metadatas", "distances"]
        )
        
        return self._format_results(results, total)
    
    def search_element_assets(
        self,
        query: Union[str, List[str]],
        module_scope: Optional[List[str]] = None,
        repo_scope: Optional[List[str]] = None,
        min_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        要素级资产检索（核心）：
        1. 优先BM25（基于_tokenized_desc字段）
        2. 不足时向量补充
        3. 范围逐步放松策略
        """
        query_text = self._prepare_query(query)
        original_query = query_text
        
        # 分词用于BM25（ChromaDB自动处理_tokenized_desc匹配）
        tokenized_query = " ".join(jieba.lcut(query_text))
        
        # 范围过滤条件构建
        def build_where(ms, rs):
            where = {}
            if ms:
                where["module"] = {"$in": ms}
            elif rs:
                where["repo"] = {"$in": rs}
            return where if where else None
        
        # 阶段1：BM25初筛（关键！利用ChromaDB原生BM25）
        where_cond = build_where(module_scope, repo_scope)
        bm25_results = self.element_coll.query(
            query_texts=[tokenized_query],  # 注意：这里用分词后的查询
            where=where_cond,
            where_document={"$contains": tokenized_query},  # ChromaDB BM25触发条件
            n_results=min_results * 2,  # 多取一些备用
            include=["metadatas", "distances"]
        )
        
        # 提取BM25有效结果（distance在BM25中代表相关性分数，越高越好）
        bm25_assets = []
        if bm25_results["ids"][0]:
            # ChromaDB BM25返回的distances是负相关分数，需转换
            for i, meta in enumerate(bm25_results["metadatas"][0]):
                # 过滤掉_tokenized_desc（内部字段）
                clean_meta = {k: v for k, v in meta.items() if not k.startswith("_")}
                bm25_assets.append(clean_meta)
        
        # 阶段2：检查是否满足最小数量
        if len(bm25_assets) >= min_results:
            self.logger.info(f"BM25检索满足需求: {len(bm25_assets)} >= {min_results}")
            return bm25_assets[:min_results]
        
        # 阶段3：向量检索补充（在相同范围内）
        vector_results = self.element_coll.query(
            query_texts=[query_text],
            where=where_cond,
            n_results=min_results,
            include=["metadatas"]
        )
        
        vector_assets = [
            {k: v for k, v in meta.items() if not k.startswith("_")}
            for meta in vector_results["metadatas"][0]
        ] if vector_results["metadatas"][0] else []
        
        # 合并去重（BM25优先）
        seen_ids = set()
        combined = []
        for asset in bm25_assets + vector_assets:
            if asset["id"] not in seen_ids:
                seen_ids.add(asset["id"])
                combined.append(asset)
        
        if len(combined) >= min_results:
            return combined[:min_results]
        
        # 阶段4：逐步放松范围（先取消module_scope，再取消repo_scope）
        if module_scope:
            self.logger.info("BM25+向量不足，放松module_scope限制")
            return self.search_element_assets(
                query=original_query,
                module_scope=None,
                repo_scope=repo_scope,
                min_results=min_results
            )
        elif repo_scope:
            self.logger.info("BM25+向量不足，放松repo_scope限制")
            return self.search_element_assets(
                query=original_query,
                module_scope=None,
                repo_scope=None,
                min_results=min_results
            )
        
        # 阶段5：终极兜底 - 全库检索
        self.logger.warning(f"全库检索仍不足 {min_results} 条，返回现有 {len(combined)} 条")
        return combined or self._fallback_full_search(query_text, min_results)
    
    def search_comprehensive(
        self,
        query: Union[str, List[str]],
        module_scope: Optional[List[str]] = None,
        repo_scope: Optional[List[str]] = None,
        min_element_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        综合检索：系统→模块→要素 三级缩小范围
        """
        query_text = self._prepare_query(query)
        
        # 步骤1：若无repo_scope，先检索相关系统
        if not repo_scope:
            systems = self.search_system_assets(query_text, ratio=0.2)
            repo_scope = [s["id"] for s in systems]
            self.logger.info(f"综合检索：通过系统检索扩展repo_scope: {len(repo_scope)} 个系统")
        
        # 步骤2：若无module_scope，用repo_scope检索模块
        if not module_scope and repo_scope:
            modules = self.search_module_assets(query_text, repo_scope=repo_scope, ratio=0.3)
            module_scope = [m["id"] for m in modules]
            self.logger.info(f"综合检索：通过模块检索扩展module_scope: {len(module_scope)} 个模块")
        
        # 步骤3：要素级检索（使用扩展后的范围）
        return self.search_element_assets(
            query=query_text,
            module_scope=module_scope,
            repo_scope=repo_scope,
            min_results=min_element_results
        )
    
    # ==================== 辅助方法 ====================
    
    def _format_results(self, results: Dict, total_count: int) -> List[Dict]:
        """标准化检索结果格式"""
        formatted = []
        for i, meta in enumerate(results.get("metadatas", [[]])[0]):
            clean_meta = {k: v for k, v in meta.items() if not k.startswith("_")}
            if "distances" in results and results["distances"][0]:
                clean_meta["similarity_score"] = 1.0 - results["distances"][0][i]  # 转为相似度
            formatted.append(clean_meta)
        self.logger.info(f"检索返回 {len(formatted)}/{total_count} 条结果")
        return formatted
    
    def _fallback_full_search(self, query: str, n: int) -> List[Dict]:
        """兜底全库检索"""
        results = self.element_coll.query(
            query_texts=[query],
            n_results=n,
            include=["metadatas"]
        )
        return [
            {k: v for k, v in meta.items() if not k.startswith("_")}
            for meta in results["metadatas"][0]
        ] if results["metadatas"][0] else []
    
    def _log_stats(self):
        """打印资产库统计信息"""
        stats = {
            "系统资产": self.system_coll.count(),
            "模块资产": self.module_coll.count(),
            "要素资产": self.element_coll.count()
        }
        self.logger.info(f"资产库统计: {json.dumps(stats, ensure_ascii=False)}")
    
    def get_library_info(self) -> Dict[str, Any]:
        """获取资产库元信息"""
        return {
            "library_id": self.library_id,
            "path": self.library_dir,
            "stats": {
                "system_count": self.system_coll.count(),
                "module_count": self.module_coll.count(),
                "element_count": self.element_coll.count()
            },
            "embedding_model": "custom" if hasattr(self, 'custom_emb') else "BGE-zh"
        }