#! /bin/sh

# The container runs as root and a self-hosted runner keeps its work
# directories between jobs.  Every file this job left in a mounted runner
# directory goes back to the owner of that directory, so that the next job of a
# non-root runner can clean it.  A failure here only warns: the job result is
# already decided.
for dir in "$GITHUB_WORKSPACE" "$HOME"; do
    if [ -n "$dir" ] && [ -d "$dir" ]; then
        uid=$(stat -c '%u' "$dir")
        gid=$(stat -c '%g' "$dir")
        find "$dir" \( ! -user "$uid" -o ! -group "$gid" \) -exec chown -h "$uid:$gid" {} + \
            || echo "warning: could not give all files in $dir back to $uid:$gid"
    fi
done

exit 0
