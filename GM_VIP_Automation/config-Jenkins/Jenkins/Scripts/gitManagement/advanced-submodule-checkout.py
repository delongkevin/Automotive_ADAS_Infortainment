import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from git import Repo, GitCommandError, Git

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

env = os.environ
is_merge = env.get("BRANCH_NAME", "").lower().endswith("-merge")


def try_fetch(git_module: Git, retries: int = 5):
    """
    Attempt to fetch all branches from the remote repository.
    Retries if the fetch fails.
    """
    for attempt in range(retries):
        try:
            git_module.fetch('--all', '--jobs=8', '--quiet', '--prune')
            break
        except GitCommandError as e:
            logger.warning(f"Fetch failed on attempt {attempt + 1}: {e}")
    else:
        logger.error("Failed to fetch after multiple attempts.")
        exit(1)


def process_submodule(submodule):
    ref_name: str
    repo = submodule.module()
    git_repo = repo.git
    submodule_name = submodule.name
    CHANGE_BRANCH = env.get('CHANGE_BRANCH', '')
    CHANGE_TARGET = env.get('CHANGE_TARGET', '')

    try_fetch(git_repo)
    refs = {ref.name for ref in repo.remotes.origin.refs}
    logger.debug(f"Submodule `{submodule_name}` refs: {refs}")

    if not (f"origin/{CHANGE_BRANCH}" in refs or f"origin/{CHANGE_TARGET}" in refs):
        logger.info(f"Submodule `{submodule_name}` has no relevant branches, skipping checkout")
        return

    branch = CHANGE_BRANCH if f'origin/{CHANGE_BRANCH}' in refs else CHANGE_TARGET

    git_repo.switch('--detach', '--quiet')
    #  if local branch exists, delete it
    heads = {head.name for head in repo.heads}
    if branch in heads:
        git_repo.branch('-D', branch)
    git_repo.checkout('-b', branch, f'origin/{branch}')
    logger.info(f"Submodule `{submodule_name}` checked out `{branch}`")

    if is_merge and branch != env['CHANGE_TARGET']:
        try:
            if f'origin/{env["CHANGE_TARGET"]}' not in refs:
                logger.warning(
                    f"Submodule `{submodule_name}` has no target branch `{env['CHANGE_TARGET']}`, skipping merge")
                return
            git_repo.merge(f'origin/{env["CHANGE_TARGET"]}')
            logger.info(f"Submodule `{submodule_name}` merged `{env['CHANGE_TARGET']}` into `{branch}`")
        except GitCommandError as e:
            logger.error(f"Merge conflict in submodule `{submodule_name}`. Resolve manually.\n{e}")
            sys.exit(1)


def git_checkout_per_job_type():
    project_root = Path(__file__).resolve().parents[4]
    repo = Repo(project_root)
    git_repo = repo.git
    env = os.environ

    if not is_merge:
        logger.info("Not a merge job, skipping submodule processing")
        return
    if "CHANGE_TARGET" in env:
        logger.info("PR job, processing submodules")
        repo.git.remote('prune', 'origin')
        try_fetch(git_repo)

        submodules = repo.submodules
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_submodule, submodule) for submodule in submodules]

            for future in futures:
                try:
                    future.result()  # This will raise an exception if one occurred in the thread
                except SystemExit as e:
                    sys.exit(e.code)  # Ensure the script exits with the expected exit code
                except Exception as e:
                    logger.error(f"Error processing submodules: {e}")
                    sys.exit(1)
        # for submodule in repo.submodules:
        #     process_submodule(submodule, env)
    else:
        logger.info("Normal Branch job, not doing anything special to submodules")


if __name__ == "__main__":
    git_checkout_per_job_type()
