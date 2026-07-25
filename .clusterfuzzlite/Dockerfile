# Copyright 2026 Skills contributors
# ClusterFuzzLite Dockerfile for Python fuzzing.
# See https://google.github.io/clusterfuzzlite/build-integration/python/

FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:3cb899359c06448afeabcffeefa9b814acb5040e391757a5790cdaa7d05ec520

COPY . $SRC/
COPY .clusterfuzzlite/build.sh $SRC/build.sh
RUN chmod +x $SRC/build.sh
