## Why

Overwriting an existing output file without warning risks unintended data loss.
Users need a clear pre-conversion check so they can choose to overwrite, rename, or abort.

## What Changes

- Detect if the chosen output file path already exists before conversion starts.
- Prompt users to overwrite, enter a new filename, or cancel the conversion.
- Update help/usage documentation to explain the new conflict handling behavior.

## Capabilities

### New Capabilities
- `output-file-conflict-handling`: Detect output file conflicts and provide user choices before conversion.

### Modified Capabilities
- None.

## Impact

- CLI conversion flow and user prompts.
- Help/usage documentation updates.
