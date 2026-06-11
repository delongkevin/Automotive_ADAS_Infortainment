import argparse
from pathlib import Path

import git

# first and only required arg is a folder path
parser = argparse.ArgumentParser(description='Add a reference repo to the Jenkinsfile')
parser.add_argument('reference_repo', type=Path, help='The path to the reference repo')
args = parser.parse_args()

reference_repo = args.reference_repo

local_repo = git.Repo(__file__, search_parent_directories=True)
project_root = Path(local_repo.working_tree_dir)

git_alternate = project_root / '.git' / 'objects' / 'info' / 'alternates'

if not reference_repo.exists():
    while not reference_repo.exists():
        print(f"Reference repo {reference_repo} does not exist on the specified machine")
        reference_repo = reference_repo.parent
        if reference_repo == Path('/'):
            break
    print(f"First valid folder {reference_repo}")
    exit(0)

if git_alternate.exists():
    with git_alternate.open('r') as f:
        existing_alternates = f.read().strip().split('\n')
    if str(reference_repo) in existing_alternates:
        print('Reference repo already exists')
    else:
        with git_alternate.open('a', newline='\n') as f:
            f.write(f"\n{reference_repo}\n")
else:
    with git_alternate.open('w', newline='\n') as f:
        f.write(f"\n{reference_repo}\n")
