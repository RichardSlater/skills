## Why

Ordinary commands such as `rg` currently need a terminal prompt and a committed approval. Those approvals are hard to use and can grant network or host execution from the repository. Normal work should just run. A command that is not already visible is looked up from a list, network belongs only to the command that needs it, and a host command is written as the command itself.

## What Changes

- **BREAKING**: Stop using exact-command approvals, including committed `.bwrap/approvals/`, as authority.
- Look up extra programs from `~/.config/bubblewrap-isolation/extra-commands`. Each line is a command name, such as `rg`. The launcher finds that program on `PATH` and binds that one file. Commands already visible in the sandbox need no line.
- Grant network per command. `~/.config/bubblewrap-isolation/network-commands` lists the command, such as `pnpm install`. That command gets network on every run. Every other command stays offline.
- Allow host execution by writing the command in `~/.config/bubblewrap-isolation/host-commands`. The only lines are `git commit` and `git push`.
- Do not copy credentials into the sandbox. Keep `pre-commit` in the sandbox.
- Ignore repository files, mount flags, and network flags as grants.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bubblewrap-command-isolation`: Replace approval records with an extra-command lookup list, a per-command network list, and a host-command list.

## Impact

`skills/bubblewrap-isolation`, `tests/bubblewrap_isolation`, and `openspec/specs/bubblewrap-command-isolation`. Existing `.bwrap/approvals/` records no longer grant authority. This change does not install a Pi harness extension; a caller that never invokes the launcher can still bypass it.
