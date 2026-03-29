import os
from pathlib import Path

def generate_mini_rag_structure():
    """
    Generate structured output documenting the mini-RAG project structure
    including all .py files in src/ and subfolders,
    plus other files with specific extensions.
    """
    PROJECT_ROOT = Path('.')
    OUTPUT_FILE = 'mini-rag-structure.txt'

    # Directories to exclude
    EXCLUDE_DIRS = {
        '__pycache__', '.git', '.venv', 'venv',
        'node_modules', 'assets', 'files'
    }

    # File extensions to always include
    INCLUDE_EXTENSIONS = ('.py', '.md', '.env', '.yml', '.yaml', '.json', '.ini', '.toml')

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# MINI-RAG PROJECT STRUCTURE #\n\n")
        f.write(f"Generated from root: {PROJECT_ROOT.resolve()}\n")
        f.write("=" * 40 + "\n\n")

        for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if not any(excl in Path(root, d).parts for excl in EXCLUDE_DIRS)]
            if any(excl in Path(root).parts for excl in EXCLUDE_DIRS):
                continue

            current_dir = Path(root)
            relative_path = current_dir.relative_to(PROJECT_ROOT)

            # Write directory header
            if str(relative_path) != '.':
                f.write(f"\n{'#' * 40}\nDIRECTORY: {relative_path}\n{'#' * 40}\n\n")
            else:
                f.write(f"{'#' * 40}\nPROJECT ROOT: {PROJECT_ROOT.resolve().name}\n{'#' * 40}\n\n")

            for file in sorted(files):
                if file == OUTPUT_FILE or file == '.gitkeep':
                    continue

                file_path = current_dir / file
                relative_file_path = file_path.relative_to(PROJECT_ROOT)

                # Include if:
                # 1. It's inside "src" and is a .py file
                # 2. OR matches allowed extensions
                is_py_in_src = file_path.suffix == '.py' and 'src' in file_path.parts
                has_include_extension = file_path.suffix in INCLUDE_EXTENSIONS

                if not is_py_in_src and not has_include_extension:
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as content_file:
                        content = content_file.read()

                    f.write(f"\n{'=' * 40}\nFILE: {relative_file_path}\n{'=' * 40}\n")
                    f.write(content.strip() + "\n\n")

                except UnicodeDecodeError:
                    f.write(f"\n{'=' * 40}\nFILE: {relative_file_path}\n{'=' * 40}\n[SKIPPED CONTENT] Binary or non-UTF-8 format\n\n")
                except Exception as e:
                    f.write(f"\n{'=' * 40}\nFILE: {relative_file_path}\n{'=' * 40}\n[ERROR READING FILE] {str(e)}\n\n")

        # Metadata section
        f.write("\n\n# PROJECT METADATA #\n--------------------\n")
        f.write("- Project Type: FastAPI RAG Implementation\n")
        f.write("- Key Components: API Endpoints, Document Processing (Chunking), Data Models, Controllers\n")
        f.write("- Notable Features: Dockerized, Configuration Management, Structured Logging (implied)\n")
        f.write("- Version: (Specify version if known, e.g., 0.1.0)\n--------------------\n")

    print(f"Project structure documentation generated: {OUTPUT_FILE}")

if __name__ == '__main__':
    generate_mini_rag_structure()
