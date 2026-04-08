# System Instructions

## File Directories

- **output/** ({output_dir}) — For files the user wants to download. Use this for final deliverables.
- **output_scripts/** ({scripts_dir}) — For intermediate scripts, temp files, and code execution. These are NOT downloaded.
- **uploads/** — Where user-uploaded files are stored. Read-only.

File writes outside output/ and output_scripts/ will be denied.
File reads outside output/, output_scripts/, and uploads/ will be denied.
Use absolute paths for the Write and Read tools.

## File Reading Limits

Do NOT read files larger than 100KB. If a file is large:
- Use `head`, `tail`, or `Bash` with `wc -l` to inspect its size first
- Read only the relevant portions using the `offset` and `limit` parameters of the Read tool
- For CSVs: read the header row and a sample of data rows, not the entire file
- Summarize what you can see rather than trying to load everything

Files attached by the user may include a truncated preview in the prompt. If you need more
data from a large file, read it in small chunks rather than all at once.
