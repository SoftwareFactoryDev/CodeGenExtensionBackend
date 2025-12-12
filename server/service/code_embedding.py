import os
import torch
from typing import List, Dict, Any

from model.UniXcoder import UniXcoder, UniXcoder_tokenize, UniXcoder_encode

class EmbeddingService:
    def __init__(self, config: Dict[str, Any]):
        os.environ['CUDA_VISIBLE_DEVICES'] = config.get('cuda_visible_devices', '0')
        
        print('Loading UniXcoder ...')
        self.model = UniXcoder(config['model_path'])
        print('UniXcoder loaded successfully')

    @torch.no_grad()
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if len(texts) > self.max_batch_size:
            results = []
            for i in range(0, len(texts), self.max_batch_size):
                batch = texts[i:i + self.max_batch_size]
                batch_results = UniXcoder_encode(self.model, batch, UniXcoder_tokenize)
                results.extend(batch_results)
            return results
        return UniXcoder_encode(self.model, texts, UniXcoder_tokenize)

