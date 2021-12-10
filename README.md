# Terrateam Action

The Terrateam action operates based on a work specification, called a Work
Manifest, which informs which operations it should execute.  It is capable of
the following operations:

- Terraform plan
- Terraform apply

The action is meant to be executed manually (via a `workflow_dispatch` event)
rather than automatically triggered.
