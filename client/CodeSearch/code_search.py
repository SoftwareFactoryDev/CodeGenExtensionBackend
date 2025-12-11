import os
from copy import deepcopy

import pandas as pd
import jieba
from rank_bm25 import BM25Okapi
from llama_index.core import Document, ServiceContext
from llama_index.retrievers.bm25 import BM25Retriever

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

    def custom_retrieval(self, query_texts, top_k=3):
        if isinstance(query_texts, str):
            query_texts = [query_texts]
        self.data['bm25_score'] = self.bm25_compute(query_texts, self.data['sum_tokenize'].tolist())
        result = self.data.sort_values('bm25_score', ascending=False)
        result = deepcopy(result.head(top_k).reset_index(drop=True))
        self.data['bm25_score'] = -1
        return result

    def llama_index_init(self, codebase_path, llama_index_path):
        documents = []
        for filename in os.listdir(codebase_path):
            if filename.endswith('.csv'):
                file_path = os.path.join(codebase_path, filename)
                df = pd.read_csv(file_path)
                if 'summary' not in df.columns:
                    print(f"警告: 文件 {filename} 中没有找到 'summary' 列，跳过该文件")
                    continue
                # 处理每一行数据
                for idx, row in df.iterrows():
                    # 获取summary作为文档内容
                    text = row['summary']
                    # 将其他列作为metadata
                    metadata = row.drop('summary').to_dict()
                    # 添加文件信息到metadata
                    metadata['source_file'] = filename
                    metadata['row_index'] = idx
                    # 创建Document对象
                    doc = Document(
                        text=text,
                        metadata=metadata
                    )
                    documents.append(doc)
        if not documents:
            self.retriever = None
            return
        service_context = ServiceContext.from_defaults()
        retriever = BM25Retriever.from_defaults(
            docstore=documents,
            service_context=service_context
        )
        self.retriever = retriever

    def retrieve_llama_index(self, query, top_k=5):
        if self.retriever is None:
            print("警告: 检索器未初始化")
            return pd.DataFrame()
        
        # 使用检索器获取相关文档
        retrieved_docs = self.retriever.retrieve(query)
        
        # 限制返回的文档数量
        retrieved_docs = retrieved_docs[:top_k]
        
        # 准备结果数据
        results = []
        for doc in retrieved_docs:
            # 创建一个字典，包含summary和所有metadata
            result = {'summary': doc.text}
            result.update(doc.metadata)
            results.append(result)
        
        # 将结果转换为DataFrame
        df = pd.DataFrame(results)
        
        return df

def code_search_custom(retriever, key_words, codebase_path, columns, top_K = 3):
    data = []
    for file in os.listdir(codebase_path):
        try:
            if columns:
                item = pd.read_csv(os.path.join(codebase_path, file), usecols=columns)
            else:
                item = pd.read_csv(os.path.join(codebase_path, file))
            item['repo_name'] = file.split('.')[00]
            if len(data) == 0:
                data = item
            else:
                data = pd.concat([data, item], ignore_index=True)
        except:
            continue
    retriever.data_import(data)
    result = retriever.custom_retrieval(key_words, top_k=top_K)
    return result


