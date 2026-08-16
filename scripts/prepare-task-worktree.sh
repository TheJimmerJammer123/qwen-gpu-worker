#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 SOURCE_REPOSITORY WORKTREE_PATH qwen/BRANCH [BASE_REF]" >&2
  exit 2
fi

source_repository="$(realpath "$1")"
worktree_path="$2"
branch="$3"
base_ref="${4:-develop}"

[[ -d "${source_repository}/.git" ]] \
  || { echo "error: source is not a primary Git repository: ${source_repository}" >&2; exit 2; }
[[ "$branch" == qwen/* ]] \
  || { echo "error: task branch must begin with qwen/" >&2; exit 2; }
[[ ! -e "$worktree_path" ]] \
  || { echo "error: worktree target already exists: ${worktree_path}" >&2; exit 2; }
git -C "$source_repository" rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null \
  || { echo "error: unknown base ref: ${base_ref}" >&2; exit 2; }
if git -C "$source_repository" show-ref --verify --quiet "refs/heads/${branch}"; then
  echo "error: local branch already exists: ${branch}" >&2
  exit 2
fi

mkdir -p "$(dirname "$worktree_path")"
git -C "$source_repository" worktree add -b "$branch" "$worktree_path" "$base_ref"
echo "task worktree ready: $(realpath "$worktree_path") branch=${branch} base=${base_ref}"
