"""Python script to parse the logs pipeline from the logs-backend repository.
This script is expected to run from a CLI, do not import it."""
import sys
import json


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


if len(sys.argv) != 2:
    print_err("This script requires a single JSON file as an argument.")
    sys.exit(1)

logs_to_metrics_mapping = json.load(sys.argv[1])
