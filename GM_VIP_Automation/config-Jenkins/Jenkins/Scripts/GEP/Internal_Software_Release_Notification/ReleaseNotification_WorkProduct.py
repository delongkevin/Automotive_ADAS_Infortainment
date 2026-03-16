import argparse
import json
import logging
import os
import re
from pathlib import Path

import git

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

repo = git.Repo(path=__file__, search_parent_directories=True)
_rev_parse = repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or repo.working_tree_dir)

build_dir = project_root / "build"


def pull_unit_versions() -> dict[str, str]:
    re_version = re.compile(r'#define (?P<unit>\w+)_VERSION\s+"(?P<version>\S+)"')
    version_info_files = list(project_root.rglob('versioninfo.h'))
    returned_versions = dict()
    for vf in version_info_files:
        logger.info(f"Found versioninfo.h file: {vf}")
        content = vf.read_text()
        matches = re_version.finditer(content)
        for match in matches:
            unit = match.group('unit')
            version = match.group('version')
            returned_versions[unit] = version
            logger.debug(f"  Found version for unit {unit}: {version}")
    logger.info(f"Collected {len(returned_versions)} unit versions.")
    return returned_versions


def grab_flashing_instructions(output_folder: Path):
    source_flashing_instructions = project_root / "tools" / "00_TRACE32" / "README.md"
    instructions_file_output = output_folder / "flashing_instructions.md"
    instructions_file_output.write_text(source_flashing_instructions.read_text())
    logger.info(f"Copied flashing instructions to {instructions_file_output}")


def release_links():
    if "TAG_NAME" not in os.environ:
        return

    origin_url = repo.remotes.origin.url
    if origin_url.startswith("git@"):
        origin_url = origin_url.replace("git@", "https://").replace(":", "/")
    tag_name = repo.git.describe(tags=True, always=True).strip()

    release_links_file = build_dir / "release_links.txt"
    release_links_file.write_text("\n".join([
        f"Formal release notes are to be found in the release folder.",
        f"Informal release notes can are found in the GitHub release page.",
        f"Test logs can be found within the release folder.",
        f"These all can be found at or through the github release page: {origin_url}/releases/tag/{tag_name}",
    ]))


def main(output_folder: Path):
    software_versions_file = output_folder / "software_versions.txt"
    versions = pull_unit_versions()
    software_versions_file.write_text("\n".join([
        "Please note the suffix (after the underscore) denotes how many commits in total are in the unit's chain.",
        "This helps provide confidence for/against unchanged version numbers having diffrent content.",
        "  - " + "\n  - ".join(f"{unit}: {version}" for unit, version in versions.items() if version),
        ""
    ]))

    grab_flashing_instructions(output_folder)
    release_links()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to facilitate 'Internal Software Release Notification'")
    parser.add_argument("--output-folder", type=Path, default=Path(__file__).parent / "output")
    args = parser.parse_args()

    args.output_folder.mkdir(parents=True, exist_ok=True)

    main(output_folder=args.output_folder)
