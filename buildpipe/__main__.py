#!/usr/bin/env python3
"""Dynamically generate Buildkite pipeline artifact based on git changes."""
from fnmatch import fnmatch
import io
import logging
import os
import re
import subprocess
import sys
from typing import List, Set

from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError


PLUGIN_PREFIX = "BUILDKITE_PLUGIN_BUILDPIPE_"

logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger("buildpipe")
log_level = os.getenv(f"{PLUGIN_PREFIX}LOG_LEVEL", "INFO")
logger.setLevel(log_level)

yaml = YAML(typ="safe")
yaml.default_flow_style = False
yaml.representer.ignore_aliases = lambda *data: True


def dump_to_string(d):
    with io.StringIO() as buf:
        yaml.dump(d, buf)
        return buf.getvalue()


def get_changed_files() -> Set[str]:
    filename = ".buildpipe/git_diff"
    branch = os.environ[f"{PLUGIN_PREFIX}CURRENT_BRANCH"]
    logger.debug("Current branch: %s", branch)
    deploy_branch = os.getenv(f"{PLUGIN_PREFIX}DEPLOY_BRANCH", "master")
    try:
        with open(filename, "r") as f:
            changed = f.readlines()
    except FileNotFoundError as e:
        logger.error("Filename %s not found: %s", filename, e)
        sys.exit(-1)
    else:
        if branch == deploy_branch:
            try:
                first_merge_break = changed.index("")
                changed = changed[:first_merge_break]
            except ValueError:
                pass

        return {line for line in changed if line}


def generate_project_steps(step: dict, projects: List[dict]) -> List[dict]:
    return [
        {
            **step,
            **{
                "label": f'{step["label"]} {project["label"]}',
                "env": {
                    "BUILDPIPE_PROJECT_LABEL": project["label"],
                    "BUILDPIPE_PROJECT_PATH": project["main_path"],
                    # Make sure step envs aren't overridden
                    **(step.get("env") or {}),
                },
            },
        }
        for project in projects
        if check_project_rules(step, project)
    ]


def check_project_affected(project: dict, changed_files: Set[str]) -> bool:
    for path in project["path"]:
        if path == ".":
            return True
        project_dirs = os.path.normpath(path).split("/")
        for changed_file in changed_files:
            changed_dirs = changed_file.split("/")
            if changed_dirs[: len(project_dirs)] == project_dirs:
                return True

    return False


def get_affected_projects(projects: List[dict]) -> List[dict]:
    changed_files = get_changed_files()
    return [
        project
        for project in projects
        if check_project_affected(project, changed_files)
    ]


def check_project_rules(step: dict, project: dict) -> bool:
    for pattern in project.get("skip", []):
        if fnmatch(step["label"], pattern):
            return False

    return True


def generate_pipeline(steps: dict, projects: List[dict]) -> dict:
    generated_steps = []
    for step in steps:
        if "env" in step and step.get("env", {}).get("BUILDPIPE_SCOPE") == "project":
            generated_steps += generate_project_steps(step, projects)
        else:
            generated_steps += [step]

    return {"steps": generated_steps}


def load_steps() -> dict:
    filename = os.environ[f"{PLUGIN_PREFIX}DYNAMIC_PIPELINE"]
    try:
        with open(filename, "r") as f:
            pipeline = yaml.load(f)
    except FileNotFoundError as e:
        logger.error("Filename %s not found: %s", filename, e)
        sys.exit(-1)
    except ScannerError as e:
        logger.error("Invalid YAML in file %s: %s", filename, e)
        sys.exit(-1)
    else:
        return pipeline["steps"]


def get_projects() -> List[dict]:
    re_label = re.compile(f"{PLUGIN_PREFIX}PROJECTS_[0-9]*_LABEL")
    project_labels = {k: v for k, v in os.environ.items() if re.search(re_label, k)}
    projects = []

    for key, label in project_labels.items():
        logger.debug("Checking %s", key)

        project = {}
        project_number = key.replace(f"{PLUGIN_PREFIX}PROJECTS_", "").replace(
            "_LABEL", ""
        )
        project["label"] = label

        main_path = os.getenv(f"{PLUGIN_PREFIX}PROJECTS_{project_number}_PATH")
        if main_path is not None:
            project["main_path"] = main_path
        else:
            # path is an array so choose the first path as the main one
            project["main_path"] = os.environ[
                f"{PLUGIN_PREFIX}PROJECTS_{project_number}_PATH_0"
            ]

        for option in ["PATH", "SKIP"]:
            logger.debug("Checking %s", option)

            re_option = re.compile(f"{PLUGIN_PREFIX}PROJECTS_{project_number}_{option}")

            values = [v for k, v in os.environ.items() if re.search(re_option, k)]

            logger.debug("Found patterns: (%s)", values)
            project[option.lower()] = values
        projects.append(project)

    return projects


if __name__ == "__main__":
    projects = get_projects()
    affected_projects = get_affected_projects(projects)
    if not affected_projects:
        logger.info("No project was affected from changes")
        sys.exit(0)
    steps = load_steps()
    pipeline = generate_pipeline(steps, affected_projects)

    with open(".buildpipe/pipeline_output", "w") as f:
        yaml.dump(pipeline, f)

    logger.debug("Pipeline:\n%s", dump_to_string(pipeline))
