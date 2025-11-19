import json

import json
import os

def remove_duplicate_content(current_file, previous_file):

    with open(current_file, 'r', encoding='utf-8') as f:
        current_data = json.load(f)
    with open(previous_file, 'r', encoding='utf-8') as f:
        previous_data = json.load(f)
    
    # 将之前文件的内容转换为集合以便比较
    previous_content = set(json.dumps(item, sort_keys=True) for item in previous_data)
    
    # 过滤掉重复的内容
    filtered_data = []
    for item in current_data:
        item_str = json.dumps(item, sort_keys=True)
        if item_str not in previous_content:
            filtered_data.append(item)
    
    # 保存处理后的结果
    with open(current_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)

def output_content(file):
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    content = ''
    for index, item in enumerate(data):
        content += "========================================\n\n"
        content += f"【{index}/{len(data)}】 " + "\n"
        content += item['req_list'] + "\n\n"
        content += "----------------------------------------\n\n"
        content += item['response'] + "\n\n"
    with open(file.replace('.json', '.txt'), 'w', encoding='utf-8') as f:
        f.write(content)

def process_result_files(directory):
    """处理目录下所有的result文件"""
    # 获取所有result文件并按编号排序
    result_files = sorted(
        [f for f in os.listdir(directory) if f.startswith('result-') and f.endswith('.json')],
        key=lambda x: int(x.split('-')[1].split('.')[0])
    )
    
    # 依次处理每个文件
    # for i in range(len(result_files)-1, 0, -1):
    #     current_file = os.path.join(directory, result_files[i])
    #     previous_file = os.path.join(directory, result_files[i-1])
    #     print(f"Processing {result_files[i]}...")
    #     remove_duplicate_content(current_file, previous_file)

    for i in range(len(result_files)):
        file = os.path.join(directory, result_files[i])
        print(f"Outputting content for {result_files[i]}...")
        output_content(file)

if __name__ == '__main__':
    # 使用示例
    result_directory = 'D:/Work/lab/20251117-20251118-一飞院/Result/RequireUnderstand'
    process_result_files(result_directory)
