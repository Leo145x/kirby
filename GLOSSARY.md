# kirby

kirby finds agent tools (skills, plugins, MCP servers) among the user's GitHub stars or on public GitHub, checks what would be installed, and installs it once the user confirms.

## Checking before install

**Pre-install check**:
Everything kirby looks at in a tool before the user decides whether to install it.
_Avoid_: scan (for the whole), security review, audit

**Pattern scan**:
The part of the pre-install check that matches the tool's files against fixed text patterns.
_Avoid_: scan (unqualified), static analysis

**Advisory lookup**:
The part of the pre-install check that looks up published vulnerabilities and security advisories for the tool and the packages it depends on.
_Avoid_: CVE scan, vulnerability scan

**Malware lookup**:
The part of the pre-install check that looks up whether the tool or a package it depends on is a known-malicious package.
_Avoid_: malware scan, virus check

**Model review**:
The part of the pre-install check in which a model reads the tool's files and reports what looks harmful. It can only add findings, never remove or lower one.
_Avoid_: AI scan, LLM judge

**Finding**:
One fact the pre-install check reports about a tool, with its severity.
_Avoid_: hit, flag, alert, issue

**Severity**:
How much weight a finding deserves: danger, warn or info.
_Avoid_: risk score, level

**Block**:
The outcome when a finding is a confirmed fact that the tool is malicious: kirby does not offer to install it.
_Avoid_: reject, deny, fail

**Unchecked**:
A part of the pre-install check that could not run for a tool, reported as such rather than as no findings: `? unchecked: …` in the dialog, and for the model review, which kirby does not run itself, `? model review: did not run`.
_Avoid_: skipped, passed

## Installing what was checked

**Pinned commit**:
The exact commit of a tool that the user was shown, and the only one kirby installs.
_Avoid_: locked version, snapshot
