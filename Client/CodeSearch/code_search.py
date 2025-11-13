import os
from copy import deepcopy

import pandas as pd
import jieba
from rank_bm25 import BM25Okapi

class NlRetriever:

    def data_import(self, data:pd.DataFrame):
        self.data = data

    def bm25_compute(self, key_words, summary) -> float:
       
        key_words_tokens = []
        for key_word in key_words:
            key_words_tokens += list(jieba.cut_for_search(key_word))
        doc_tokens = list(jieba.cut_for_search(summary.replace('，','').replace('。','').replace('！','').replace('？','')))
        bm25 = BM25Okapi([doc_tokens])
        score = bm25.get_scores(key_words_tokens)
        return score[0]
    
    def retrieval(self, query_texts, top_k=20):
        self.data['bm25_score'] = self.data['summary'].apply(
            lambda x: self.bm25_compute(query_texts, x)
        )
        result = self.data.sort_values('bm25_score', ascending=True)
        result = deepcopy(result.head(top_k).reset_index(drop=True))
        return result

def code_search(key_words, top_K = 20):
    retriever = NlRetriever()
    data = []
    for file in os.listdir('./CodeBaseBuild/data'):
        item = pd.read_csv('./CodeBaseBuild/data/' + file)
        item['repo_name'] = file.split('.')[00]
        if len(data) == 0:
            data = item
        else:
            data - pd.concat([data, item])
    retriever.data_import(data)
    result = retriever.retrieval(key_words, top_k=top_K)
    return result
