# Copyright 2026 Skills contributors
# ClusterFuzzLite Dockerfile for Python fuzzing.
# See https://google.github.io/clusterfuzzlite/build-integration/python/

FROM gcr.io/oss-fuzz-base/base-builder-python

COPY . $SRC/skills
WORKDIR $SRC/skills

RUN pip3 install atheris

COPY fuzzing/ $SRC/skills/fuzzing/
