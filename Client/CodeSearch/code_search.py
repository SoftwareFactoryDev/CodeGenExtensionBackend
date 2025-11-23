import os
from copy import deepcopy

import pandas as pd
import jieba
from rank_bm25 import BM25Okapi

class NlRetriever:

    def data_import(self, data:pd.DataFrame):
        self.data = data

    def bm25_compute(self, key_words, doc_tokens) -> float:
       
        key_words_tokens = []
        for key_word in key_words:
            key_words_tokens += list(jieba.cut_for_search(key_word))
        bm25 = BM25Okapi(doc_tokens)
        score = bm25.get_scores(key_words_tokens)
        return score
    
    def retrieval(self, query_texts, top_k=20):
        if isinstance(query_texts, str):
            query_texts = [query_texts]
        self.data['bm25_score'] = self.bm25_compute(query_texts, self.data['sum_tokenize'].tolist())
        result = self.data.sort_values('bm25_score', ascending=False)
        result = deepcopy(result.head(top_k).reset_index(drop=True))
        self.data['bm25_score'] = -1
        return result

def code_search(codebase_path, key_words, top_K = 20):
    retriever = NlRetriever()
    data = []
    for file in os.listdir(codebase_path):
        item = pd.read_csv(os.path.join(codebase_path, file))
        item['repo_name'] = file.split('.')[00]
        if len(data) == 0:
            data = item
        else:
            data - pd.concat([data, item])
    retriever.data_import(data)
    result = retriever.retrieval(key_words, top_k=top_K)
    return result
