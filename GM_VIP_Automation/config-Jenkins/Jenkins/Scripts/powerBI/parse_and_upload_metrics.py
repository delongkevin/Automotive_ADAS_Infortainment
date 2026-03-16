import argparse
import json
import pathlib
import re
from glob import glob

from SCons.Tool import suffix

from uploader import DatabaseManager

Default_Project_Table = "B3_D2H7960_BuidStats"  # Yes, the project ID here is wrong, but it'd be slightly problematic to change it at this point here.  No issues are expected for this.


def main():
    matched_files = glob(file_path)
    file_contents = ""
    for file in matched_files:
        file_contents += pathlib.Path(file).read_text(errors='ignore')

    metrics_dict = parse_file(file_contents, violation_parser)

    databaseManager = DatabaseManager()
    databaseManager.insert_data(table, metrics_dict)


def parse_file(file_contents, parser_name: str):
    if parser_name.lower() in parsers:
        return parsers[parser_name](file_contents)
    else:
        raise ValueError(f"Invalid violation parser, please choose from {parsers.keys()}")


def parser_compiler(file_contents) -> dict:
    pattern = re.compile(r".+:\d+:\d+: (warning|error): .+")
    matches = pattern.findall(file_contents)
    retDict = {
        f'Compiler_Warn{suffix}': matches.count("warning"),
        f'Compiler_Err{suffix}': matches.count("error")
    }
    return retDict


def parser_qac(file_contents: str) -> dict:
    # file_contents is poorly done, wth dicts like {absdcvs}{ascasc}{ascas}, which need the strign separated into different json items then merged.
    splits = file_contents.replace('}{', '}|||||{').split('|||||')
    jsons = [json.loads(split) for split in splits]
    consolidate = {}
    for j in jsons:
        for k, v in j.items():
            consolidate[k] = consolidate.get(k, 0) + v
    data = {f'QAC_{k}{suffix}': v for k, v in consolidate.items()}
    return data


parsers = {
    "gcc": parser_compiler,
    "qac": parser_qac,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("violation_parser", help=f"The violation parser to use, select from {parsers.keys()}")
    parser.add_argument("file_path", help="The file to parse")
    parser.add_argument("--table", help="The table to insert the data into", default=Default_Project_Table)
    parser.add_argument("--suffix", help="The suffix to add to the table name", default=None)

    args = parser.parse_args()
    violation_parser = args.violation_parser
    file_path = args.file_path
    table = args.table
    suffix = f"_{args.suffix}" if args.suffix else ""

    main()
