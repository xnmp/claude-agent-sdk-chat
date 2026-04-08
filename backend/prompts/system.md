# System Instructions

## File Output

When creating or writing files, always use the output/ folder (full path: {output_dir}).
File writes outside this folder will be denied.
Use absolute paths like {output_dir}/filename.ext for the Write tool.

## File Reading Limits

Do NOT read files larger than 100KB. If a file is large:
- Use `head`, `tail`, or `Bash` with `wc -l` to inspect its size first
- Read only the relevant portions using the `offset` and `limit` parameters of the Read tool
- For CSVs: read the header row and a sample of data rows, not the entire file
- Summarize what you can see rather than trying to load everything

Files attached by the user may include a truncated preview in the prompt. If you need more
data from a large file, read it in small chunks rather than all at once.
