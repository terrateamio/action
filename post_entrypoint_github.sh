#! /bin/sh

# The container runs as root and a self-hosted runner keeps its work
# directories between jobs.  Every file this job left in the workspace goes
# back to the owner of the workspace, so that the next job of a non-root runner
# can clean it.  $HOME keeps its owner: it holds the tenv cache, which must
# persist between jobs.  A failure here only warns: the job result is already
# decided.
dir="$GITHUB_WORKSPACE"
if [ -n "$dir" ] && [ -d "$dir" ]; then
    uid=$(stat -c '%u' "$dir")
    gid=$(stat -c '%g' "$dir")
    find "$dir" \( ! -user "$uid" -o ! -group "$gid" \) -exec chown -h "$uid:$gid" {} + \
        || echo "warning: could not give all files in $dir back to $uid:$gid"
fi

exit 0
