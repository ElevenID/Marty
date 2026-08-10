#!/usr/bin/env bash
set -euo pipefail

architecture="${1:-x86_64}"
destination="${2:-native-wheels}"
core_tag="${MARTY_CORE_NATIVE_TAG:-v0.1.37}"
credentials_tag="${MARTY_CREDENTIALS_NATIVE_TAG:-v0.1.50}"

case "$architecture" in
  x86_64|aarch64)
    architectures=("$architecture")
    ;;
  all)
    architectures=(x86_64 aarch64)
    ;;
  *)
    echo "Unsupported native wheel architecture: $architecture" >&2
    exit 2
    ;;
esac

mkdir -p "$destination"

download_and_verify() {
  local repository="$1"
  local tag="$2"
  local package="$3"
  local version="${tag#v}"
  local arch pattern name expected actual

  for arch in "${architectures[@]}"; do
    pattern="${package}-${version}-*manylinux*${arch}.whl"
    gh release download "$tag" \
      --repo "$repository" \
      --pattern "$pattern" \
      --dir "$destination" \
      --clobber

    shopt -s nullglob
    local matches=("$destination"/${package}-${version}-*manylinux*${arch}.whl)
    shopt -u nullglob
    if [ "${#matches[@]}" -ne 1 ]; then
      echo "Expected exactly one $package $version $arch wheel, found ${#matches[@]}" >&2
      exit 1
    fi

    name="$(basename "${matches[0]}")"
    expected="$(gh release view "$tag" --repo "$repository" --json assets \
      --jq ".assets[] | select(.name == \"$name\") | .digest")"
    if [[ ! "$expected" =~ ^sha256:[0-9a-f]{64}$ ]]; then
      echo "Release asset $repository@$tag/$name has no valid SHA-256 digest" >&2
      exit 1
    fi
    actual="sha256:$(sha256sum "${matches[0]}" | cut -d ' ' -f1)"
    if [ "$actual" != "$expected" ]; then
      echo "Digest mismatch for $repository@$tag/$name" >&2
      exit 1
    fi
  done
}

download_and_verify ElevenID/marty-core "$core_tag" marty_iso18013
download_and_verify ElevenID/marty-core "$core_tag" marty_verification_py
download_and_verify ElevenID/marty-credentials "$credentials_tag" marty_rs
