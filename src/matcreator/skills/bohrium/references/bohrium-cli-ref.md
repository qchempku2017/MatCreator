# Bohrium CLI Reference


## Job Submit

```bash
bohr job submit \
  --job_name "Name" \
  --project_id <id> \
  --machine_type "<type>" \
  --image_address "<registry>" \
  --command "<cmd>" \
  --log_file "<file>" \
  --backward_files "<f1>,<f2>" \
  --max_run_time <minutes> \
  --input_directory "./"
```

Options:
- `--job_name`: name of the job
- `--project_id`: project ID
- `--image_address`: image address on bohrium.
- `--machine_type`: `c2_m4_cpu`, `c4_m15_1`, `c32_m64_cpu`, or with GPU: `1 * NVIDIA L20_48g`, `1 * NVIDIA V100_32g`
- `--max_run_time`: in minutes. Default is unlimited.
- `--command`: command to run in the container.
- `--backward_files`: comma-separated string (NOT array). Should include all critical result files,
   log files and directories. Supports "*" wildcard. Example: `"output,log,*.csv"`.
- `--input_directory`: local dir to upload as job input. Usually uses the current directory `./`,
   which means all files in the current directory will be uploaded, and you have to make sure to `cd`
   into the right directory before running `bohr job submit` from there.
- `--nnode`: number of compute nodes to use for the job (default 1, more than 1 not tested and not recommended)
- `--max_reschedule_times`: auto-retry count if submission fails (default 0)

> **Note**: `bohr job submit` prints out the job ID and the job group ID when finished.
> Keep these IDs along with the job name for quick reference in job management.

## Job Management

```bash
bohr job list -j <jobGroupId>              # List jobs in group (active only by default)
bohr job list -j <jobGroupId> --json       # JSON output
bohr job list -j <jobGroupId> -i           # Finished only
bohr job list -j <jobGroupId> -f           # Failed only
bohr job list -j <jobGroupId> -r           # Running only
bohr job list -j <jobGroupId> -p           # Pending only
bohr job list -j <jobGroupId> -s           # Scheduling only
bohr job list -j <jobGroupId> -d           # Stopped only
bohr job log -j <jobId> -o ./dir/          # Download logs
bohr job download -j <jobId> -o ./dir/     # Download results
bohr job kill -j <jobId>                   # Kill job
```

> **Note**: Default listing shows active jobs only — completed jobs are **not** shown unless `-i` is used.

## Job Group

```bash
bohr job_group create -n <name> -p <project_id>    # Create group, returns job_group_id
bohr job_group list --json                          # List groups
bohr job_group download -j <groupId> -o ./dir/     # Download all results for group
bohr job_group terminate <groupId>                  # Terminate all jobs in group
bohr job_group delete <groupId>                     # Delete group
```

Submit jobs under a group via `--job_group_id <groupId>` in `bohr job submit`.

## Project & Node

```bash
bohr project list --json                   # List projects (non-interactive)
bohr node list                             # List compute nodes
bohr image list                            # List available images
```

## Notes

- API endpoint `openapi.dp.tech` is slow — wrap commands with `timeout 60-120`.
  When submitting very large directories, it may require even longer timeouts.
- `bohr project list` without `--json` opens interactive TUI that hangs in non-terminal
- Job logs include the log file as specified in `bohr job submit` options and `STDOUTERR` (shell stdout/stderr)
- Results are downloaded as a zip file to the specified output directory, may need to extract.
