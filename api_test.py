import requests
from typing import List

data = {
    'type' : 'semantic',
    'code' : """  BrotliSharedDictionary* dict = 0;
  if (!alloc_func && !free_func) {
    dict = (BrotliSharedDictionary*)malloc(sizeof(BrotliSharedDictionary));
  } else if (alloc_func && free_func) {
    dict = (BrotliSharedDictionary*)alloc_func(
        opaque, sizeof(BrotliSharedDictionary));
  }
  if (dict == 0) {
    return 0;
  }

  /* TODO(eustas): explicitly initialize all the fields? */
  memset(dict, 0, sizeof(BrotliSharedDictionary));

  dict->context_based = BROTLI_FALSE;
  dict->num_dictionaries = 1;
  dict->num_word_lists = 0;
  dict->num_transform_lists = 0;

  dict->words[0] = BrotliGetDictionary();
  dict->transforms[0] = BrotliGetTransforms();

  dict->alloc_func = alloc_func ? alloc_func : BrotliDefaultAllocFunc;
  dict->free_func = free_func ? free_func : BrotliDefaultFreeFunc;""",
  'err' : [
      {
        'line' : 2,
        'col' : 7,
        'desp' : 'R-1-2-4 引起二义性理解的 逻辑表达式，必须使用括号显式说明优先级顺序。',
      },
      {
        'line' : 4,
        'col' : 10,
        'desp' : 'R-1-4-1 在if-else if语句中必须使用else分支。',
      }
  ]
}

# 接口 URL（请替换为实际部署地址）
url = "http://localhost:14514/fix"

response = requests.post(url, json=data)

# 输出结果
print("Status Code:", response.status_code)
print("Response JSON:", response.json())