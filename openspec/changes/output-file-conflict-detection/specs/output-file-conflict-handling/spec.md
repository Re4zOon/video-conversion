## ADDED Requirements

### Requirement: Detect existing output file before conversion
The system SHALL check whether the resolved output file path already exists before starting a conversion.

#### Scenario: Output file does not exist
- **WHEN** a conversion is started and the output file path does not exist
- **THEN** the conversion proceeds without prompting

#### Scenario: Output file exists
- **WHEN** a conversion is started and the output file path already exists
- **THEN** the system prompts the user to choose how to proceed before conversion begins

### Requirement: Prompt for conflict resolution
The system SHALL present options to overwrite the existing file, enter a new filename, or cancel the conversion.

#### Scenario: User chooses overwrite
- **WHEN** the output file exists and the user selects overwrite
- **THEN** the conversion proceeds and replaces the existing file

#### Scenario: User chooses rename
- **WHEN** the output file exists and the user selects rename
- **THEN** the system prompts for a new output filename and rechecks for conflicts

#### Scenario: User chooses cancel
- **WHEN** the output file exists and the user selects cancel
- **THEN** the conversion is aborted without modifying files

### Requirement: Document conflict handling
The system SHALL document the output file conflict handling behavior in help or usage documentation.

#### Scenario: User requests help
- **WHEN** the user views CLI help or usage documentation
- **THEN** the conflict handling options are described
