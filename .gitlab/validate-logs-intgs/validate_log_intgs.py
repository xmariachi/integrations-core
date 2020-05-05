"""Python script to parse the logs pipeline from the logs-backend repository.
This script is expected to run from a CLI, do not import it."""
import sys
import json
from typing import List
import re
import yaml
import os

LOGS_BACKEND_INTGS_ROOT = os.environ['LOGS_BACKEND_INTGS_ROOT']
INTEGRATIONS_CORE = os.environ['INTEGRATIONS_CORE_ROOT']


class CheckDefinition(object):
    def __init__(self, dir_name, name, integration_id, log_collection):
        self.dir_name = dir_name
        self.name = name
        self.integration_id = integration_id
        self.log_collection = log_collection
        self.log_source_name = None
        self.source_name_readme = self.get_log_source_in_readme()

    def set_log_source_name(self, log_source_name):
        self.log_source_name = log_source_name

    def get_log_source_in_readme(self):
        readme_file = os.path.join(INTEGRATIONS_CORE, self.dir_name, "README.md")
        with open(readme_file, 'r') as f:
            content = f.read()

        code_sections = re.findall(r'`+.*?`+', content, re.DOTALL)
        sources = set(re.findall(r'(?:"source"|source): "?(\w+)"?', "\n".join(code_sections), re.MULTILINE))
        if len(sources) == 0:
            # print_err(f"No source defined in readme for integration {self.name}")
            return None
        if len(sources) > 1:
            raise Exception(f"More than one source defined in readme for integration {self.name}")

        return list(sources)[0]

    def is_self(self, other_check_name):
        candidates = [self.dir_name.lower(), self.name.lower(), self.integration_id.lower()]
        if self.source_name_readme:
            candidates.append(self.source_name_readme.lower())
        if other_check_name.lower() in candidates:
            return True

        return False

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, ", ".join(f"{k}={v}" for k, v in self.__dict__.items()))


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def get_all_checks() -> List[CheckDefinition]:
    check_dirs = [
        d for d in os.listdir(INTEGRATIONS_CORE)
        if not d.startswith('.')
        and os.path.isfile(os.path.join(INTEGRATIONS_CORE, d, "manifest.json"))
    ]
    check_dirs.sort()
    manifests = []
    for check in check_dirs:
        with open(os.path.join(INTEGRATIONS_CORE, check, "manifest.json"), 'r') as f:
            manifests.append(json.load(f))

    integration_names = [m['name'] for m in manifests]
    integration_ids = [m['integration_id'] for m in manifests]
    log_collection_enabled = ['log collection' in m['categories'] for m in manifests]

    for i in range(len(check_dirs)):
        yield CheckDefinition(check_dirs[i], integration_names[i], integration_ids[i], log_collection_enabled[i])


def get_all_log_pipelines_ids():
    files = [os.path.join(LOGS_BACKEND_INTGS_ROOT, f) for f in os.listdir(LOGS_BACKEND_INTGS_ROOT)]
    files = [f for f in files if os.path.isfile(f)]
    files.sort()
    for file in files:
        with open(file, 'r') as f:
            yield yaml.load(f)['id']


def get_check_for_pipeline(log_source_name, agt_intgs_checks):
    for check in agt_intgs_checks:
        if check.is_self(log_source_name):
            return check
    return None


if len(sys.argv) != 2:
    print_err("This script requires a single JSON file as an argument.")
    sys.exit(1)

with open(sys.argv[1]) as f:
    logs_to_metrics_mapping = json.load(f)

all_checks = list(get_all_checks())
checks = []
for pipeline_id in get_all_log_pipelines_ids():
    check = get_check_for_pipeline(pipeline_id, all_checks)
    if not check:
        continue
    check.set_log_source_name(pipeline_id)
    checks.append(check)


validation_errors_per_check = {}

for check in checks:
    if not check.log_collection:
        print_err(f"Check {check.name} has a log pipeline but does not define 'log collection' in its manifest file.")
    if not check.source_name_readme:
        print_err(f"Check {check.name} has a log pipeline but does not appear to document log collection with the correct source name in the README.")
    elif not check.source_name_readme == check.log_source_name:
        print_err(f"Check {check.name} uses 'source: {check.source_name_readme}' in the README but log pipeline uses {check.log_source_name}.")

# Filter to only agt integrations checks
import code
code.interact(local=locals())
