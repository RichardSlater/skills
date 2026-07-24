#!/bin/bash -eu
# Copyright 2026 Skills contributors
# ClusterFuzzLite build script for Python fuzzers.
# Compile each fuzz target with pyinstaller and create executable wrappers
# so ClusterFuzzLite can discover them (binary names must not have extensions).

for fuzzer in $(find $SRC/fuzzing -name 'fuzz_*.py'); do
  fuzzer_basename=$(basename -s .py "$fuzzer")
  fuzzer_package=${fuzzer_basename}.pkg

  # Compile into a standalone pyinstaller package.
  pyinstaller --distpath $OUT --onefile --name "$fuzzer_package" "$fuzzer"

  # Create an executable shell wrapper (no .py extension) that CFL can find.
  # Omit LD_PRELOAD — pure-Python fuzzers with no C extensions.
  cat > "$OUT/$fuzzer_basename" <<WRAPPER
#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
this_dir=\$(dirname "\$0")
ASAN_OPTIONS=\$ASAN_OPTIONS:symbolize=1:external_symbolizer_path=\$this_dir/llvm-symbolizer:detect_leaks=0 \\
\$this_dir/$fuzzer_package "\$@"
WRAPPER
  chmod +x "$OUT/$fuzzer_basename"
done
