# Integrating another package manager

The launcher currently accepts only the names listed in SKILL.md. The ecosystems below are **candidates, not implemented grants**: adding an unknown name to `global.package_managers` does not enable it.

## Common candidates

| Ecosystem | Manager / tool installer | What to investigate |
| --- | --- | --- |
| Go | Modules and `go install` | Installed binaries (`GOBIN` or `GOPATH/bin`); Go runtime/toolchain, module cache and build cache only if needed. Many compiled Go tools need just the existing single-file `extra-commands` grant. See [Go modules](https://go.dev/ref/mod). |
| PHP | Composer | PHP runtime/extensions, project `vendor/bin` or global Composer vendor tree. Keep `auth.json` separate from package data. See [Composer CLI](https://getcomposer.org/doc/03-cli.md). |
| C / C++ | Conan, vcpkg | Installed package trees, native toolchain/shared libraries, downloads and binary caches. These are primarily build dependencies, not just CLI shims. See [Conan environment](https://docs.conan.io/2/reference/environment.html) and [vcpkg caching](https://learn.microsoft.com/en-us/vcpkg/consume/binary-caching-overview). |
| Java / JVM | Maven, Gradle | JDK, Maven artifact repository, Gradle distributions and caches. Separate Maven `settings.xml`, Gradle properties/init scripts and credentials from required runtime data. See [Maven repositories](https://maven.apache.org/repositories/local.html) and [Gradle layout](https://docs.gradle.org/current/userguide/directory_layout.html). |
| C# / .NET | NuGet and `dotnet tool` | .NET host/runtime (SDK only when needed), global tool shims and their backing store, NuGet packages. Keep NuGet authentication configuration separate. See [dotnet tool install](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-tool-install). |

Other candidates include RubyGems/Bundler, Dart pub, Haskell Cabal/Stack, Elixir Hex/Mix, Perl CPAN/cpanm, R renv, and Julia Pkg. Yarn and pipx are also common gaps in the already-supported JavaScript/Python ecosystems. Each needs its own layout check; ecosystem membership alone does not make another manager's grant cover it.

## Lightweight integration workflow

1. **Start with one failing tool invocation.** Record the manager/version, installation method, exact argv, and failure. Prefer a project-local installation already covered by the project mount, or `extra-commands` for a self-contained executable. Add manager support only when those existing paths do not meet the need; agree the supported layout with the operator first.
2. **Map the files it actually needs.** Consult current official documentation, inspect the executable/shebang and resolved symlink targets as data, and identify tool binaries, backing packages, runtimes, shared libraries, and caches separately. If a native path query is needed (for example `go env` or `composer global config bin-dir --absolute`), ask the operator to run the trusted query. The launcher must not execute managers or project wrappers on the host to discover paths. Treat returned paths as evidence, not mount authority.
3. **Choose the smallest prepared-tool layout.** List exact read-only roots and required sandbox environment variables. Include symlink targets and runtime data, not just the wrapper. Mount a symlinked root at the path tools expect so relative links keep working inside the sandbox; do not flatten those links. Omit authentication files and unrelated home data; do not mount an entire manager home, prefix root, or any path that contains the home or credential directories. Document custom paths and installation modes that remain unsupported. A dependency cache is not automatically needed to run an already-built tool.
4. **Extend the existing launcher, not a new framework.** In `scripts/run-isolated.sh`, add the name to the package-manager validation in `apply_config_grants` and a case in `prepare_package_managers`. Reuse `package_root`, `package_executable`, `PACKAGE_PATH_DIRS`, and `PACKAGE_ENV`. Preserve the private HOME and the existing network/host grants. Do not add arbitrary-path config, automatic downloads, host discovery commands, or a writable host cache as shortcuts.
5. **Verify the original use case.** Extend the existing fixture check in `tests/bubblewrap_isolation/test_skill_contract.py`; run the manager version probe and one real prepared tool through the launcher with temporary operator config. Confirm dependency loading, `execution=sandbox`, `network=off`, read-only package data, and exclusion of any nearby authentication config. Report unavailable real installations as fixture-only rather than claiming live verification. Update the SKILL.md directory table and applicable OpenSpec artifacts, run the contract tests and pre-commit, and sync the installed skill/reference files.
6. **Enable only after acceptance.** Explain that all data in the proposed roots becomes readable, name the exact `global.package_managers` string, and follow SKILL.md's explicit-acceptance config-write workflow. Verify and sync the implementation before appending the new name; older launchers will reject it. Report the resulting launcher status line.

## When read-only caches are insufficient

Some managers write lock files, build products, indexes, or first-run state even for offline operations. Network access does not fix a read-only filesystem. Keep build output and disposable state in the project/private temporary home, use a manager-supported separate writable cache, or prepare a disposable copy of required cache data. If the manager cannot separate those writes from the host installation, report that limitation and use a project-local installation or disposable environment rather than making the shared host cache writable.

Integration is complete when the original prepared tool works within the agreed layout, the focused checks pass, and the documentation accurately states what is and is not supported. A successful `--version` alone is not enough.
