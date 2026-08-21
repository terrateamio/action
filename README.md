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
| `TERRATEAM_PLUGIN_CACHE` | `false` | When set to `1` or `true`, every `init` in the run shares one Terraform/OpenTofu provider plugin cache, so a provider is downloaded once per run instead of once per dirspace. It is ignored, and the run behaves as before, when the repository already sets `TF_PLUGIN_CACHE_DIR` or a `plugin_cache_dir` in a CLI configuration file (`TF_CLI_CONFIG_FILE`, `TOFU_CLI_CONFIG_FILE`, `~/.terraformrc`, `~/.tofurc`), or when the cache directory cannot be written to. Providers are only taken from the cache for a dirspace whose `.terraform.lock.hcl` is committed. |
| `TERRATEAM_PLUGIN_CACHE_DIR` | `/tmp/terrateam-plugin-cache` | Where `TERRATEAM_PLUGIN_CACHE` puts the shared cache.  It is created if it does not exist. |
