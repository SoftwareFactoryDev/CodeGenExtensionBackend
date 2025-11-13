import torch
import torch.nn as nn
from transformers import RobertaTokenizer, RobertaModel, RobertaConfig

class UniXcoder(nn.Module):

    def __init__(self, model_name):
     
        super(UniXcoder, self).__init__()
        self.tokenizer = RobertaTokenizer.from_pretrained(model_name)
        self.config = RobertaConfig.from_pretrained(model_name)
        self.tokenizer.add_tokens(["<mask0>"],special_tokens=True)
        self.model = RobertaModel.from_pretrained(model_name, config=self.config)
    
    def forward(self, source_ids):   
        """ Obtain token embeddings and sentence embeddings """
        mask = source_ids.ne(self.config.pad_token_id)
        token_embeddings = self.model(source_ids,attention_mask = mask.unsqueeze(1) * mask.unsqueeze(2))[0]
        sentence_embeddings = (token_embeddings * mask.unsqueeze(-1)).sum(1) / mask.sum(-1).unsqueeze(-1)
        return token_embeddings, sentence_embeddings

    def tokenize(self, inputs, mode="<encoder-only>", max_length=512, padding=False):

        assert mode in ["<encoder-only>", "<decoder-only>", "<encoder-decoder>"]
        assert max_length < 1024
        
        tokenizer = self.tokenizer
        
        tokens_ids = []
        for x in inputs:
            tokens = tokenizer.tokenize(x)
            if mode == "<encoder-only>":
                tokens = tokens[:max_length-4]
                tokens = [tokenizer.cls_token,mode,tokenizer.sep_token] + tokens + [tokenizer.sep_token]                
            elif mode == "<decoder-only>":
                tokens = tokens[-(max_length-3):]
                tokens = [tokenizer.cls_token,mode,tokenizer.sep_token] + tokens
            else:
                tokens = tokens[:max_length-5]
                tokens = [tokenizer.cls_token,mode,tokenizer.sep_token] + tokens + [tokenizer.sep_token]
                
            tokens_id = tokenizer.convert_tokens_to_ids(tokens)
            if padding:
                tokens_id = tokens_id + [self.config.pad_token_id] * (max_length-len(tokens_id))
            tokens_ids.append(tokens_id)
        return tokens_ids

def UniXcoder_tokenize(model, text, param={}):

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    tokens_ids = model.tokenize([text],mode="<encoder-only>")
    return tokens_ids

def UniXcoder_encode(model, text, tokenizer):

    if isinstance(text, str):
        print(f'Tokenizing string: {text}')
        token_list = tokenizer(model, text)
        print(f'Embedding string: {text}')
        vector = model(token_list)[1].detach().cpu().numpy().tolist()
    elif isinstance(text, list):
        print(f'Tokenizing list: {len(text)}')
        token_list = torch.tensor([tokenizer(model, t) for t in text]).cuda()
        if len(text) == 1:
            token_list = torch.squeeze(token_list, dim=1)
        print(f'Embedding list: {len(text)}')
        vector = model(token_list)[1].detach().cpu().numpy().tolist()
        # vector = [model(token)[1].detach().cpu().numpy().tolist() for token in token_list]
    return vector