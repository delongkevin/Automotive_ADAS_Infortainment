import argparse
import logging
import os
import re
import sys
from pathlib import Path

from git import GitCommandError, UnmergedEntriesError, Repo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

script_dir = Path(__file__).resolve().parent
script_repo = Repo(path=script_dir, search_parent_directories=True)
_rev_parse = script_repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or script_repo.working_tree_dir)
repo = Repo(project_root)

parser = argparse.ArgumentParser(description="""
    When dealing with a git project with many submodules that need alignment, merge conflicts will frequently occur at the top level.
    This project is intended to run in a Jenkins CI/CD environment.  On "PR Head" jobs, it will check for conflicts ONLY on submodules.
    If that scenario is met, it will resolve the conflicts tasking your specified pointers.
""")
args = parser.parse_args()

BULLET = "\n\t• "


def capture_default_branch(repo: Repo) -> str:
    remote = repo.remotes.origin
    remote.fetch("HEAD")
    for ref in remote.refs:
        if ref.name.endswith("HEAD"):
            return ref.ref.name.removeprefix("origin/")
    raise ValueError("Could not determine default branch")


def get_submodule_paths(repo):
    return [submodule.path for submodule in repo.submodules]


def is_repo_dirty(repo):
    submodules = get_submodule_paths(repo)
    diff_list = [diff for diff in repo.git.diff('--name-only').splitlines() if (diff not in submodules)]
    if diff_list:
        diffs = '\n\t- ' + '\n\t- '.join(diff_list)
        logger.info(f"You have changed files{diffs}")
        return True
    return False


def convert_repo_to_ssh(repo):
    remote_url: str = repo.remote().url
    if "https://" in remote_url:
        new_url = "git@" + remote_url.removeprefix('https://').replace('/', ':', 1)
        logger.info(f"Converting remote URL to ssh.\n\tOld URL: {remote_url}\n\tNew URL: {new_url}")
        repo.remote().set_url(new_url)
    else:
        logger.info("Remote URL is already in SSH format")


def main():
    if not CHANGE_TARGET:
        logger.warning("Not running in Jenkins on a PR build. Exiting.")
        sys.exit(0)
    if is_repo_dirty(repo):
        logger.warning(f"Your repo is dirty, please commit or stash changes before running this script.")
        sys.exit(1)
    convert_repo_to_ssh(repo)

    try:
        repo.git.fetch("origin", f"{CHANGE_TARGET}")
        merge_output = repo.git.merge(f"origin/{CHANGE_TARGET}", "--no-commit", "--no-ff", f"-m Resolving submodule pointer conflict against branch origin/{CHANGE_TARGET}")
        if "Note: Fast-forwarding submodule" in merge_output:
            logger.info(f"Fast-forwarded submodules during merge against branch `origin/{CHANGE_TARGET}`, later should not be detected as a conflict from GitHub.")
            repo.git.merge("--continue")
            repo.remote().push(f"HEAD:{CHANGE_BRANCH}")
            exit(0)
        if not "Already up to date" in merge_output:
            repo.git.merge("--abort")  # Clean up merge state if merge succeeds
        logger.info(f"No merge conflicts detected against branch `origin/{CHANGE_TARGET}`")
        exit(0)
    except (GitCommandError, UnmergedEntriesError) as e:
        re_conflict = re.compile(r"CONFLICT \((?P<type>.+?)\): Merge conflict in (?P<filepath>.+)")
        conflicts = re_conflict.findall(e.stdout)
        submodule_conflicts = [f for t, f in conflicts if t == "submodule"]
        content_conflicts = [f for t, f in conflicts if t == "content"]
        other_conflicts = [f for t, f in conflicts if t not in ["submodule", "content"]]

        logger.info(f"Found {len(submodule_conflicts)} submodule pointer conflicts: {BULLET}{BULLET.join(submodule_conflicts)}")
        logger.info(f"Found {len(content_conflicts)} content conflicts: {BULLET}{BULLET.join(content_conflicts)}")
        logger.info(f"Found {len(other_conflicts)} other conflicts: {BULLET}{BULLET.join(other_conflicts)}")

        if other_conflicts:
            logger.error(f"Unhandled conflict types: {other_conflicts}, please contact the project integrator to update {__file__}")
            exit(1)
        if content_conflicts:
            logger.warning(f"We're only handling submodule conflicts, but there are content conflicts: {BULLET}{BULLET.join(content_conflicts)}.\n\tPlease resolve these manually")
            exit(0)
        if submodule_conflicts:
            for submodule_conflict in submodule_conflicts:
                logger.info(f"Resolving submodule pointer conflict in {submodule_conflict}")
                repo.git.add(submodule_conflict)  # Use ours for submodule pointer conflicts

        repo.git.merge("--continue")
        repo.remote().push(f"HEAD:{CHANGE_BRANCH}")


if __name__ == "__main__":
    os.environ["GIT_EDITOR"] = "true"  # This will remove interactive prompts. required for "git merge --continue"

    IN_JENKINS = os.getenv("CI", "false").lower() == "true"

    CHANGE_BRANCH = os.getenv("CHANGE_BRANCH") or repo.active_branch.name
    CHANGE_TARGET = os.getenv("CHANGE_TARGET") or capture_default_branch(repo)
    main()