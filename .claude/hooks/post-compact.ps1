# SessionStart(compact) hook: re-inject the latest stream checkpoint after a
# compaction so play continues without re-reading files or re-scouting the map.
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$state = Join-Path $root ".claude\stream-state.md"
Write-Output "Context was just compacted. Latest stream checkpoint follows; continue the stream from it (CLAUDE.md has the operating rules). Re-run harness/checkpoint.py after the next decision."
if (Test-Path $state) {
  Get-Content -Raw -Encoding UTF8 $state
} else {
  Write-Output "(No checkpoint yet - run: cd harness; ../runtime/python checkpoint.py `"notes`")"
}
