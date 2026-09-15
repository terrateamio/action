# Terrateam Action

The Terrateam action operates based on a work specification, called a Work
Manifest, which informs which operations it should execute.  It is capable of
the following operations:

- Terraform plan
- Terraform apply

The action is meant to be executed manually (via a `workflow_dispatch` event)
rather than automatically triggered.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TERRATEAM_INFRACOST_COMPACT_LOG` | `false` | When set to `1` or `true`, replaces the full Infracost diff JSON logged to the Actions console with a single summary line (`projects`, `prev`, `curr`, `diff` monthly costs). Useful for large monorepos where the JSON output spans hundreds of thousands of lines. The full diff JSON is still computed and sent to the Terrateam API regardless of this setting. |
