#!/usr/bin/env bats

load "$BATS_PATH/load.bash"

setup() {
  _GET_CHANGED_FILE='log --name-only --no-merges --pretty=format: origin..HEAD'
  stub git "${_GET_CHANGED_FILE} : echo 'project0/app.py'"
}

teardown() {
  unstub git
}


@test "Checks projects affected" {
  export BUILDKITE_PLUGIN_BUILDPIPE_DYNAMIC_PIPELINE="tests/dynamic_pipeline.yml"
  export BUILDKITE_PLUGIN_BUILDPIPE_PROJECTS_0_LABEL="project0"
  export BUILDKITE_PLUGIN_BUILDPIPE_PROJECTS_0_PATH="project0"
  export BUILDKITE_PLUGIN_BUILDPIPE_PROJECTS_1_LABEL="project1"
  export BUILDKITE_PLUGIN_BUILDPIPE_PROJECTS_1_PATH_0="project1"
  export BUILDKITE_PLUGIN_BUILDPIPE_PROJECTS_1_PATH_1="project0"
  export BUILDKITE_PLUGIN_BUILDPIPE_LOG_LEVEL="DEBUG"
  export BUILDKITE_BRANCH="not_master"
  export BUILDKITE_PLUGIN_BUILDPIPE_CURRENT_BRANCH="not_master"

  # TODO: figure out to use hooks/command
  # run hooks/command
  run python3 "$PWD/buildpipe"

  assert_success
  assert_output --partial "label: test project0"
  assert_output --partial "label: test project1"
  assert_output --partial "make tag"
}
