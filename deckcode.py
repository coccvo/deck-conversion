import os
import sys
import urllib.request
import urllib.error
import time
import json
import ctypes
from pathlib import Path
from typing import Optional, Dict, List, Tuple 

# ==================== 配置 ====================
CONFIG = {
    'folder_path': "deck",
    'formal_file': "to-formal.txt",
    'pre_file': "to-pre.txt",
    'url_formal': [
        "https://hk.gh-proxy.org/https://raw.githubusercontent.com/coccvo/deck-conversion/main/to-formal.txt",                            
        "https://raw.githubusercontent.com/coccvo/deck-conversion/refs/heads/main/to-formal.txt", 
        "https://wget.la/https://raw.githubusercontent.com/coccvo/deck-conversion/main/to-formal.txt",                           
        "https://hub.glowp.xyz/https://raw.githubusercontent.com/coccvo/deck-conversion/main/to-formal.txt",
    ],
    'url_pre': [
        "https://hk.gh-proxy.org/https://raw.githubusercontent.com/coccvo/deck-conversion/main/to-pre.txt",                            
        "https://raw.githubusercontent.com/coccvo/deck-conversion/refs/heads/main/to-pre.txt", 
        "https://wget.la/https://raw.githubusercontent.com/coccvo/deck-conversion/main/to-pre.txt",                           
        "https://hub.glowp.xyz/https://raw.githubusercontent.com/coccvo/deck-conversion/main/to-pre.txt",
    ],
    'cache_file': ".update_cache.json",
    'max_retries': 2
}

# 更新任务列表：(文件名, URL)
UPDATE_TASKS = [
    (CONFIG['formal_file'], CONFIG['url_formal']),
    (CONFIG['pre_file'], CONFIG['url_pre']),
]

# ==================== Windows 隐藏文件操作 ====================
def set_hidden_attribute(filepath: str, hidden: bool = True) -> bool:
    """设置或取消文件的隐藏属性 (仅 Windows 有效)"""
    if sys.platform != 'win32':
        return False
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
        if attrs == -1:
            return False
        
        FILE_ATTRIBUTE_HIDDEN = 0x02
        if hidden:
            new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN
        else:
            new_attrs = attrs & ~FILE_ATTRIBUTE_HIDDEN
        
        return ctypes.windll.kernel32.SetFileAttributesW(filepath, new_attrs) != 0
    except Exception:
        return False

def save_cache(cache_data: Dict[str, str]):
    """保存缓存到文件，并在 Windows 上设置为隐藏"""
    cache_file = CONFIG['cache_file']
    
    # Windows: 写入前先取消隐藏，防止写入失败
    if sys.platform == 'win32' and os.path.exists(cache_file):
        set_hidden_attribute(cache_file, hidden=False)
    
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
        
        # Windows: 写入后重新设置为隐藏
        if sys.platform == 'win32':
            set_hidden_attribute(cache_file, hidden=True)
    except Exception as e:
        print(f"警告：无法保存缓存文件：{e}")

# ==================== 缓存操作 ====================
def load_cache() -> Dict[str, str]:
    """加载 ETag 缓存"""
    cache_file = CONFIG['cache_file']
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}

# ==================== 文件下载更新 ====================
def download_from_url(url: str, local_etag: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    从单个URL下载文件
    返回: (成功标志, 内容, 新ETag)
    """
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'YDK-Update-Tool/1.0')
        if local_etag:
            req.add_header('If-None-Match', local_etag)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
            try:
                text_content = content.decode('utf-8')
            except UnicodeDecodeError:
                text_content = content.decode('gbk', errors='ignore')
            
            new_etag = response.headers.get('ETag', '').strip()
            return True, text_content, new_etag

    except urllib.error.HTTPError as e:
        if e.code == 304:
            return True, None, None  # 304表示未修改
        return False, None, None
    except Exception:
        return False, None, None

def check_and_update_file(filename: str, url_list: List[str], cache: Dict[str, str]) -> bool:
    """检查并更新文件 (使用 ETag 机制，支持多URL自动切换)"""
    local_etag = cache.get(filename)
    
    # 过滤掉空的URL
    valid_urls = [url.strip() for url in url_list if url.strip()]
    
    if not valid_urls:
        print(f"[错误] {filename} 没有配置有效的URL。")
        return False
    
    # 尝试每个URL
    for url_index, url in enumerate(valid_urls):
        url_label = f"URL#{url_index+1}" if url_index > 0 else "主URL"
        
        for attempt in range(CONFIG['max_retries']):
            try:
                success, content, new_etag = download_from_url(url, local_etag)
                
                if success:
                    # 304未修改
                    if content is None:
                        print(f"[{url_label}] {filename} 已是最新。")
                        return True
                    
                    # 写入文件
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    if new_etag:
                        cache[filename] = new_etag
                    
                    if url_index == 0:
                        print(f"[下载] {filename} 已更新。")
                    else:
                        print(f"[下载] {filename} 已更新 (使用备用{url_index})。")
                    return True
                
            except Exception as e:
                wait_time = (attempt + 1) * 2
                print(f"[警告] {filename} ({url_label}) 下载失败 ({attempt+1}/{CONFIG['max_retries']}): {e}")
                
                if attempt < CONFIG['max_retries'] - 1:
                    time.sleep(wait_time)
        
        # 当前URL所有重试都失败，尝试下一个备用URL
        if url_index < len(valid_urls) - 1:
            print(f"[切换] {filename} 尝试下一个备用URL...")
            time.sleep(1)
            continue
    
    # 所有URL都失败
    if os.path.exists(filename):
        print(f"[提示] 使用本地旧版 {filename}。")
        return True
    print(f"[错误] 无法下载初始文件 {filename}。")
    return False

# ==================== 替换规则加载  ====================
def load_replacements() -> Optional[Dict[str, str]]:
    """
    加载对照表替换规则。
    新增功能：
    1. 自动检测右侧密码，若小于8位则前方补0。
    2. 同时注册“原版短码”和“补零长码”两个键，实现双向匹配。
    """
    replacements = {}
    files_config = [
        (CONFIG['formal_file'], False), # formal: key(左)->val(右)
        (CONFIG['pre_file'], True),     # pre: val(右)->key(左)，即 右->左
    ]
    
    for filename, swap in files_config:
        if not os.path.exists(filename):
            continue
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # 1. 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split('\t')
                    
                    # 2. 格式检查
                    if len(parts) >= 2:
                        left_val = parts[0].strip()   # 左侧内容 (通常是卡号)
                        right_val = parts[1].strip()  # 右侧内容 (通常是密码)
                        
                        if not left_val or not right_val:
                            print(f"[警告] {filename} 第 {line_num} 行包含空键或空值，已跳过。")
                            continue
         
                        # 如果是 pre_file (swap=True): 我们希望用 密码(右) 去匹配 ydk，替换为 卡号(左)
                        # 所以: match_key = right_val, replace_val = left_val
                        if swap:
                            match_key = right_val
                            replace_val = left_val
                        else:
                            # formal_file: 用 卡号(左) 匹配，替换为 密码(右) (通常不需要补零，但为了逻辑统一保留结构)
                            match_key = left_val
                            replace_val = right_val

                        # 注册原始版本
                        replacements[match_key] = replace_val

                        # 如果 match_key 是纯数字且长度小于8，生成补零版本并注册
                        if match_key.isdigit() and len(match_key) < 8:
                            padded_key = match_key.zfill(8) # 前方补0到8位
                            
                            # 只有当补零后的key与原key不同时才注册，避免重复
                            if padded_key != match_key:
                                replacements[padded_key] = replace_val
                 

                    else:
                        print(f"[警告] {filename} 第 {line_num} 行格式不正确，已跳过：{line}")
                        
        except Exception as e:
            print(f"[错误] 读取 {filename} 出错：{e}")
    
    return replacements if replacements else None

# ==================== YDK 文件处理 ====================
def process_ydk_files(replacements: Dict[str, str]) -> List[str]:
    """处理 deck 目录下的所有 ydk 文件 (按行精确匹配)"""
    deck_path = Path(CONFIG['folder_path'])
    ydk_files = list(deck_path.rglob('*.ydk'))
    updated_files = []
    
    for ydk in ydk_files:
        try:
            content = ydk.read_text(encoding='utf-8')
            lines = content.splitlines()
            new_lines = []
            changed = False
            
            for line in lines:
                stripped = line.strip()
                if stripped in replacements:
                    new_lines.append(replacements[stripped])
                    changed = True
                else:
                    new_lines.append(line)
            
            if changed:
                ydk.write_text('\n'.join(new_lines), encoding='utf-8')
                updated_files.append(str(ydk.relative_to(deck_path)))
                
        except Exception as e:
            print(f"[错误] 处理文件 {ydk} 时异常：{e}")
    
    return updated_files

# ==================== 主程序 ====================
def main() -> int:
    if not os.path.exists(CONFIG['folder_path']):
        print(f"[错误] 未找到 '{CONFIG['folder_path']}' 文件夹。")
        print("       请将此程序放在游戏目录下运行。")
        input("\n按回车键退出...")
        return 1

    cache = load_cache()

    critical_failure = False
    for fname, url in UPDATE_TASKS:
        if not check_and_update_file(fname, url, cache):
            if not os.path.exists(fname):
                critical_failure = True

    save_cache(cache)

    if critical_failure:
        print("\n[致命错误] 缺少必要的对照表文件且无法下载。")
        input("\n按回车键退出...")
        return 1

    replacements = load_replacements()
    
    if not replacements:
        print("[警告] 替换规则为空，跳过卡组处理。")
    else:
        updated_files = process_ydk_files(replacements)
        
        print("\n" + "=" * 30)
        if updated_files:
            print(f"【更新完成】共修改 {len(updated_files)} 个卡组文件：")
            for fname in updated_files:
                print(f"  - {fname}")
        else:
            print("【更新完成】所有卡组文件均为最新，无需修改。")
        print("=" * 30)

    print("\n按回车键退出...")
    input()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[中断] 用户取消操作。")
        sys.exit(130)
    except Exception as e:
        print(f"\n[严重错误] {e}")
        input("\n按回车键退出...")
        sys.exit(1)
