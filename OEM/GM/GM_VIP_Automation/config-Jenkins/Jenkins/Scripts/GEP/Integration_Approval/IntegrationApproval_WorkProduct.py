import argparse
import logging
import os
from pathlib import Path

import git

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

repo = git.Repo(path=__file__, search_parent_directories=True)
_rev_parse = repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or repo.working_tree_dir)


def main(output_folder: Path):
    origin_url = repo.remotes.origin.url
    if origin_url.startswith("git@"):
        origin_url = origin_url.replace("git@", "https://").replace(":", "/")
    tag_name = repo.git.describe(tags=True, always=True).strip()

    integration_approvals_file = output_folder / "Integration_Approvals.txt"
    integration_approvals_file.write_text("\n".join([
        f"Bidirectional traceability is a distinct intention within our process.",
        f"As such, the 'review and approval of each integration request' can be found as part of each integration",
        f"From the commit message, the release, the task, they are linked together.",
        f"As such, the following github release page can be followed to grab this information: {origin_url}/releases/tag/{tag_name}",
    ]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to facilitate 'Internal Software Release Notification'")
    parser.add_argument("--output-folder", type=Path, default=Path(__file__).parent / "output")
    args = parser.parse_args()

    if "TAG_NAME" not in os.environ:
        exit(0)

    args.output_folder.mkdir(parents=True, exist_ok=True)
    main(output_folder=args.output_folder)
