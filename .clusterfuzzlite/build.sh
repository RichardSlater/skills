#!/bin/bash -eu
# Copyright 2026 Skills contributors
# ClusterFuzzLite build script: copies fuzz targets into $OUT.

for fuzzer in $SRC/fuzzing/fuzz_*.py; do
  fuzzer_name=$(basename "$fuzzer")
  cp "$fuzzer" "$OUT/$fuzzer_name"
done
