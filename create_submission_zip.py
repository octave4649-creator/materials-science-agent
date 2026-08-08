"""
创建赛事提交用的 zip 压缩包
排除：缓存文件、运行产物、开发计划、解析中间产物、密钥等
"""
import os
import zipfile

PROJECT_ROOT = r'e:\github\世界人工智能开源大赛\赛道三：前沿探索AIforResearch'
OUTPUT_ZIP = os.path.join(PROJECT_ROOT, 'materials-science-agent-submission.zip')

# 需要排除的目录模式（相对于项目根目录）
EXCLUDE_DIRS = {
    '__pycache__',
    '.pytest_cache',
    '.ruff_cache',
    '.venv',
    'venv',
    '.idea',
    '.vscode',
    'data/cache',
    'data/parsed',
    'results',
    '.trae/plan',
    '.trae/skills',
    '.git',
}

# 需要排除的文件模式（精确匹配文件名）
EXCLUDE_FILE_PATTERNS = {
    '.env',
    '.env.local',
    '.DS_Store',
    '*.pyc',
    '*.pyo',
    '*.pyd',
    '*.key',
    'credentials.json',
    '*.log',
    '*.tmp',
    '.gitignore',
    'create_submission_zip.py',  # 排除打包脚本自身
    'convert_docx_to_md.py',      # 排除临时转换脚本
}

# 需要排除的文件扩展名（赛事上传以文档形式单独提交，代码包不含）
EXCLUDE_EXTENSIONS = {
    '.docx',
    '.doc',
    '.pptx',
    '.ppt',
    '.pdf',
    '.zip',
    '.rar',
    '.7z',
}

# 目录是否应该被排除
def should_exclude_dir(rel_path: str) -> bool:
    parts = rel_path.replace('\\', '/').split('/')
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    # 检查完整路径
    normalized = rel_path.replace('\\', '/')
    for excl in EXCLUDE_DIRS:
        if normalized.startswith(excl) or f'/{excl}/' in f'/{normalized}/':
            return True
    return False

# 文件是否应该被排除
def should_exclude_file(filename: str, abs_file: str) -> bool:
    # 排除输出 zip 文件本身
    if os.path.normpath(abs_file) == os.path.normpath(OUTPUT_ZIP):
        return True
    # 精确匹配
    if filename in EXCLUDE_FILE_PATTERNS:
        return True
    # 扩展名匹配（小写判断）
    ext = os.path.splitext(filename)[1].lower()
    if ext in EXCLUDE_EXTENSIONS:
        return True
    if filename.endswith('.pyc') or filename.endswith('.pyo') or filename.endswith('.pyd'):
        return True
    if filename.endswith('.key'):
        return True
    # .env 前缀
    if filename.startswith('.env'):
        return True
    return False

def main():
    total_files = 0
    excluded_files = 0
    excluded_dirs_count = 0

    print(f'项目根目录: {PROJECT_ROOT}')
    print(f'输出文件: {OUTPUT_ZIP}')
    print('开始扫描...\n')

    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
            rel_dir = os.path.relpath(dirpath, PROJECT_ROOT)
            if rel_dir == '.':
                rel_dir = ''

            # 排除目录
            if rel_dir and should_exclude_dir(rel_dir):
                excluded_dirs_count += 1
                # 清空 dirnames 防止进入子目录
                dirnames[:] = []
                continue

            for filename in filenames:
                rel_file = os.path.join(rel_dir, filename) if rel_dir else filename
                abs_file = os.path.join(dirpath, filename)

                if should_exclude_file(filename, abs_file):
                    excluded_files += 1
                    continue

                # zip 内使用统一正斜杠
                arcname = rel_file.replace('\\', '/')
                zf.write(abs_file, arcname)
                total_files += 1

                if total_files % 50 == 0:
                    print(f'  已打包 {total_files} 个文件...')

    size_mb = os.path.getsize(OUTPUT_ZIP) / (1024 * 1024)
    print('\n===== 打包完成 =====')
    print(f'打包文件数: {total_files}')
    print(f'排除目录数: {excluded_dirs_count}')
    print(f'排除文件数: {excluded_files}')
    print(f'压缩包大小: {size_mb:.2f} MB')
    print(f'输出路径: {OUTPUT_ZIP}')

    if size_mb > 1200:
        print('\n⚠️  警告：文件超过 1200MB 单文件限制！')
    else:
        print('\n✅ 大小符合赛事上传限制 (< 1200MB)')

if __name__ == '__main__':
    main()
