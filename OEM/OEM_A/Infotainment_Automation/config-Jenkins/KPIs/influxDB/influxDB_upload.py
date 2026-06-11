import argparse
import json
import logging
import os
from pathlib import Path

import git
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

script_dir = Path(__file__).resolve().parent
_repo = git.Repo(path=script_dir, search_parent_directories=True)
_rev_parse = _repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or _repo.working_tree_dir)
repo = git.Repo(project_root)
if os.environ.get("BRANCH_NAME"):
    branch = os.environ.get("BRANCH_NAME")
else:
    branch = repo.active_branch.name



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sample_kpis = {
    "Connection": {
        "type": "InfluxDB",
        "host": "",
        "token": "",
        "org": "",
        "bucket": ""
    },
    "Point": {
        "Name": "",
        "Tags": {
            "branch": ""
        },
        "Fields": {
        }
    }
}


def get_args():
    parser = argparse.ArgumentParser(
        description="""
        This script uploads KPI data to an InfluxDB instance from a JSON file.
        The JSON file should contain:
        - Connection details for the InfluxDB instance (host, token, org, bucket)
        - A Point with a name, tags, and fields containing KPI values.
        If no file is provided, it defaults to 'KPIs.json'.
        """,
        epilog="""
        Example usage:
        python script.py KPIs.json
        If omitted, 'KPIs.json' will be used by default.
        If neither the provided nor default file exists, the script will provide a sample JSON structure in that location.
        """
    )
    parser.add_argument(
        "file",
        type=str,
        nargs='?',
        default="KPIs.json",
        help="The JSON file to ingest (default: KPIs.json)"
    )
    parsed = parser.parse_args()
    if not Path(parsed.file).exists():
        with open(parsed.file, "w") as f:
            json.dump(sample_kpis, f, indent=4)
        logger.warning(f"Provided file `{parsed.file}` does not exist. A sample JSON file has been created at that location.")
    return parsed

def write_data(json_data):
    connection = json_data["Connection"]
    point_data = json_data["Point"]

    client = InfluxDBClient(url=connection["host"], token=connection["token"], org=connection["org"])
    write_api = client.write_api(write_options=SYNCHRONOUS)

    point = Point(point_data["Name"])
    if "Tags" in point_data:
        for tag, value in point_data["Tags"].items():
            if not value:
                logger.warning(f"Expected Tag `{tag}` to have a value, but got None. Skipping...")
                continue
            point = point.tag(tag, value)
    for field, value in point_data["Fields"].items():
        point = point.field(field, value)

    write_api.write(bucket=connection["bucket"], org=connection["org"], record=point)
    logger.info("Data successfully written to InfluxDB")

def read_data(json_data):
    connection = json_data["Connection"]
    client = InfluxDBClient(url=connection["host"], token=connection["token"], org=connection["org"])
    query_api = client.query_api()

    query = f"""from(bucket: "{connection['bucket']}")
     |> range(start: -2m)
     |> filter(fn: (r) => r._measurement == "{json_data['Point']['Name']}")"""

    tables = query_api.query(query, org=connection["org"])

    for table in tables:
        for record in table.records:
            logger.info(f"Record: {record}")

if __name__ == "__main__":
    args = get_args()
    with open(args.file, "r") as f:
        json_data = json.load(f)
    json_data["Point"]["Tags"]["branch"] = branch
    write_data(json_data)

    logger.info("Reading data after writing...")
    read_data(json_data)
