import re
import argparse
from pathlib import Path

def preprocess_build_log(input_path: Path, subpath: str, workspace: str):
    content = input_path.read_text().split('\n')

    new_content = []
    for line in content:
        line = line.replace(subpath, workspace)  # Replace env.SUBPATH with env.WORKSPACE
        line = line.replace('C:\\WINDRI~1\\COMPIL~1\\DIAB-5~1.0\\', 'C:\\WindRiver\\compilers\\diab-5.9.9.0\\')  # Fix WindRiver pathing

        line = re.sub(r'"no file", line \d+:', '"no file", line 1:', line)
        line = re.sub(r'\$\$\d+', '$$--redacted--', line)
        line = re.sub(r'^.*?\\(sw\\.*)$', r'"\1', line)  # relative path to avoid jenkins out of workspace issue

        new_content.append(line)

    input_path.write_text('\n'.join(new_content))


def main():
    parser = argparse.ArgumentParser(description="Preprocess build log by applying regex replacements and path substitutions.")
    parser.add_argument('input_file', type=Path, help="Path to the input build log file.")
    parser.add_argument('subpath', type=str, help="The SUBPATH to replace.")
    parser.add_argument('workspace', type=str, help="The WORKSPACE to replace SUBPATH with.")
    args = parser.parse_args()

    preprocess_build_log(args.input_file, args.subpath, args.workspace)


if __name__ == "__main__":
    main()
