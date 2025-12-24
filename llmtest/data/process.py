import os
import re
import json
import shutil

def req_exact(req_dir):

    pattern = re.compile(r'^[A-Z_]+(?:-[A-Z_]+)*-\d+$')

    for filename in os.listdir(req_dir):

        if not filename.endswith(".txt"):
            continue

        file_path = os.path.join(req_dir, filename)

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        result = []
        current_id = None
        current_content = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if pattern.match(line):
                if current_id is not None:
                    result.append(
                        {"ID": current_id, "Content": "\n".join(current_content)}
                    )
                current_id = line
                current_content = []
            else:
                current_content.append(line)

        if current_id is not None:
            result.append({"ID": current_id, "Content": "\n".join(current_content)})

        json_path = os.path.join(req_dir, f"{os.path.splitext(filename)[0]}.json")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
            
        os.remove(file_path)
