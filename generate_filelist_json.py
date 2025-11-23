import os
import json
import time
from datetime import datetime

BASE_DIR = os.path.join(os.getcwd(), 'docs', 'swagger')
SOURCES = ['taifex', 'tpex', 'twse']

def safe_load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def get_summary_map(src_dir):
    summary_map = {}
    mani_path = os.path.join(src_dir, 'manifest.json')
    mani = safe_load_json(mani_path)
    entries = []
    if isinstance(mani, dict) and isinstance(mani.get('files'), list):
        entries = mani['files']
    elif isinstance(mani, list):
        entries = mani
    for e in entries:
        if isinstance(e, str):
            continue
        if isinstance(e, dict):
            fname = e.get('file') or e.get('path')
            summ = e.get('summary')
            if fname and summ:
                summary_map[fname] = summ
    return summary_map


def extract_body_count(data):
    if isinstance(data, dict):
        resp = data.get('response')
        if isinstance(resp, dict):
            body = resp.get('body')
            if isinstance(body, list):
                return len(body)
    return 0


def main():
    entries = []
    for src in SOURCES:
        src_dir = os.path.join(BASE_DIR, src)
        if not os.path.isdir(src_dir):
            continue
        summary_map = get_summary_map(src_dir)
        for name in os.listdir(src_dir):
            if not name.lower().endswith('.json'):
                continue
            if name == 'manifest.json':
                continue
            full_path = os.path.join(src_dir, name)
            # size
            try:
                size_bytes = os.path.getsize(full_path)
                size_kb = round(size_bytes / 1024.0, 1)
            except Exception:
                size_kb = None
            # count
            data = safe_load_json(full_path)
            count = extract_body_count(data) if data is not None else None
            # summary/display
            summary = summary_map.get(name)
            display = f"{summary} ({name})" if summary else name
            entries.append({
                'src': src,
                'file': name,
                'summary': summary,
                'display': display,
                'count': count,
                'sizeKB': size_kb,
            })
    out = {
        'generatedAt': datetime.utcnow().isoformat() + 'Z',
        'files': entries,
    }
    out_path = os.path.join(BASE_DIR, 'filelist.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"filelist.json generated: {out_path}")

if __name__ == '__main__':
    main()