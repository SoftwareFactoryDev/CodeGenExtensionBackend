import os
from copy import deepcopy
import json
import math
import ast
import time
import pandas as pd
import jieba
from rank_bm25 import BM25Okapi
from llama_index.core import Document, ServiceContext
from llama_index.retrievers.bm25 import BM25Retriever
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from client.CodeBaseBuild.llm_gen import generate_api
from client.CodeBaseBuild.llm_gen import nlp_emb_api
from client.CodeSearch.util import check_repo_json
from app.logger import logger_global
class NlRetriever:

    def data_import(self, asset_data: pd.DataFrame, info_data: list = []):
        self.asset_data = deepcopy(asset_data)
        self.info_data = deepcopy(info_data)

    def bm25_compute(self, key_words, doc_tokens) -> float:

        key_words_tokens = []
        for key_word in key_words:
            tokens = list(jieba.cut_for_search(key_word))
            tokens = [token for token in tokens if token not in self.stopwords]
            key_words_tokens.extend(tokens)
        bm25 = BM25Okapi(doc_tokens)
        score = bm25.get_scores(key_words_tokens)
        return score

    def cosine_distances(self, target_vector, vector_array):

        target_vector = np.array(target_vector)
        vector_array = np.array(vector_array)

        similarities = cosine_similarity([target_vector], vector_array)[0]

        return similarities

    def nlp_consine_compute(self, key_words, doc_embeddings, url) -> float:
        start_itme = time.time()
        key_words_embedding = nlp_emb_api(key_words, url)
        end_time = time.time()
        print(f"嵌入用时 {end_time-start_itme}")
        cos = self.cosine_distances(key_words_embedding, doc_embeddings)
        return cos

    def load_stopwords(self, stopword_path):
        with open(stopword_path, "r", encoding="utf-8") as f:
            stopwords = f.read().splitlines()
        self.stopwords = stopwords

    def custom_retrieval(self, query_texts, emb_url, top_k=3):
        # find repo
        start_itme = time.time()
        repo_embs = [info["desp_emb"] for info in self.info_data]
        repo_rank = zip(
            self.info_data,
            self.nlp_consine_compute(query_texts, repo_embs, url=emb_url),
        )
        end_time = time.time()
        print(f"系统级资产相似度计算用时 {end_time-start_itme}")
        start_itme = time.time()
        repo_rank = sorted(repo_rank, key=lambda x: x[1], reverse=True)
        end_time = time.time()
        print(f"系统级资产排序用时 {end_time-start_itme}")
        if not(repo_rank[0][1] <= 0):
            repo_rank = repo_rank[: math.ceil(len(self.info_data) * 0.8)]

        # find module
        start_itme = time.time()
        module_infos = []
        for repo in repo_rank:
            rname = repo[0]["name"]
            module_infos.extend([{"repo_name": rname, **m} for m in repo[0]["modules"]])
        module_embs = [info["desp_emb"] for info in module_infos]
        module_rank = zip(
            module_infos, self.nlp_consine_compute(query_texts, module_embs, emb_url)
        )
        end_time = time.time()
        print(f"模块级资产相似度计算用时 {end_time-start_itme}")
        start_itme = time.time()
        module_rank = sorted(module_rank, key=lambda x: x[1], reverse=True)
        end_time = time.time()
        print(f"模块级资产排序用时 {end_time-start_itme}")
        if not(module_rank[0][1] <= 0):
            module_rank = module_rank[: math.ceil(len(self.info_data) * 0.8)]

        # find asset
        start_itme = time.time()
        if isinstance(query_texts, str):
            query_texts = [query_texts]
        repo_names = [m[0]["repo_name"] for m in module_rank]
        module_names = [m[0]["name"] for m in module_rank]
        data_mask = deepcopy(
            self.asset_data["repo_name"].isin(repo_names)
            & self.asset_data["module"].isin(module_names)
        )
        data_mask = self.asset_data[data_mask]
        end_time = time.time()
        print(f"函数级资产筛选用时 {end_time-start_itme}")
        start_itme = time.time()
        data_mask["sim_score"] = self.bm25_compute(
            query_texts, data_mask["sum_tokenize"].tolist()
        )
        end_time = time.time()
        print(f"函数级资产BM25用时 {end_time-start_itme}")
        start_itme = time.time()
        data_mask = data_mask.sort_values("sim_score", ascending=False)
        result = deepcopy(data_mask.head(top_k).reset_index(drop=True))
        end_time = time.time()
        print(f"函数级资产BM25排序用时 {end_time-start_itme}")
        if (result["sim_score"] <= 0).all():
            start_itme = time.time()
            if isinstance(query_texts, list) and len(query_texts) == 1:
                query_texts = query_texts[0]
            
            data_mask["sim_score"] = (
                self.nlp_consine_compute(
                    query_texts, data_mask["sum_embedding"].apply(lambda x: ast.literal_eval(x)).to_list(), emb_url
                )
                if isinstance(query_texts, str)
                else [
                    self.nlp_consine_compute(
                        query_text, data_mask["sum_embedding"].apply(lambda x: ast.literal_eval(x)).to_list(), emb_url
                    )
                    for query_text in query_texts
                ]
            )
            end_time = time.time()
            print(f"函数级资产COS用时 {end_time-start_itme}")
            start_itme = time.time()
            data_mask = data_mask.sort_values("sim_score", ascending=False)
            result = deepcopy(data_mask.head(top_k).reset_index(drop=True))
            end_time = time.time()
            print(f"函数级资产COS排序用时 {end_time-start_itme}")
        return result


def code_search_custom(retriever, key_words, codebase_path, columns, emb_url, top_K=3):
    logger = deepcopy(logger_global)
    asset_data = []
    info_data = []
    start_itme = time.time()
    for file in os.listdir(codebase_path):
        if file.endswith(".csv"):
            try:
                if columns:
                    item = pd.read_csv(
                        os.path.join(codebase_path, file), usecols=columns
                    )
                else:
                    item = pd.read_csv(os.path.join(codebase_path, file))
                if len(asset_data) == 0:
                    asset_data = item
                else:
                    asset_data = pd.concat([asset_data, item], ignore_index=True)
            except Exception as e:
                logger.error(f"读取数据错误:{file}\n{str(e)}")
                continue
        elif file.endswith(".json"):
            try:
                if not check_repo_json(os.path.join(codebase_path, file)):
                    continue
                with open(
                    os.path.join(codebase_path, file), "r", encoding="utf-8"
                ) as f:
                    item = json.load(f)
                info_data.append(item)
            except Exception as e:
                logger.error(f"读取数据错误:{file}\n{str(e)}")
                continue
    retriever.data_import(asset_data, info_data)
    end_time = time.time()
    print(f"数据加载用时：{end_time-start_itme}")
    result = retriever.custom_retrieval(key_words, top_k=top_K, emb_url=emb_url)
    return result
