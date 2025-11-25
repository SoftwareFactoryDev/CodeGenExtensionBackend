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
            tokens = list(jieba.cut_for_search(key_word))
            tokens = [token for token in tokens if token not in self.stopwords]
            key_words_tokens.extend(tokens)
        bm25 = BM25Okapi(doc_tokens)
        score = bm25.get_scores(key_words_tokens)
        return score
    
    def load_stopwords(self, stopword_path):
        with open(stopword_path, 'r', encoding='utf-8') as f:
            stopwords = f.read().splitlines()
        self.stopwords = stopwords

    def retrieval(self, query_texts, top_k=3):
        if isinstance(query_texts, str):
            query_texts = [query_texts]
        self.data['bm25_score'] = self.bm25_compute(query_texts, self.data['sum_tokenize'].tolist())
        result = self.data.sort_values('bm25_score', ascending=False)
        result = deepcopy(result.head(top_k).reset_index(drop=True))
        self.data['bm25_score'] = -1
        return result

def code_search(retriever, key_words, top_K = 3):

    result = retriever.retrieval(key_words, top_k=top_K)
    return result
