import os
import json
import pandas as pd

def req_load(folder_path):
    all_data = []

    for filename in os.listdir(folder_path):
        if not filename.endswith('.json'):
            continue
        file_path = os.path.join(folder_path, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                all_data.extend(data)
            else:
                print(f"警告: 文件 {filename} 中的数据不是列表格式，已跳过")
                
        except Exception as e:
            print(f"处理文件 {filename} 时出错: {str(e)}")
            continue
    
    if all_data:
        df = pd.DataFrame(all_data)
        return df
    else:
        print("警告: 没有找到有效的数据")
        return pd.DataFrame()