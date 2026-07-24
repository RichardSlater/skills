# Copyright 2026 Skills contributors
# ClusterFuzzLite Dockerfile for Python fuzzing.
# See https://google.github.io/clusterfuzzlite/build-integration/python/

FROM gcr.io/oss-fuzz-base/base-builder-python

COPY . $SRC/
COPY .clusterfuzzlite/build.sh $SRC/build.sh
RUN chmod +x $SRC/build.sh
