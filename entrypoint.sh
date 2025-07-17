#! /bin/sh

# Set PATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Adding /usr/local/proxy/bin to the PATH for accessing additional tools, if needed
export PATH="$PATH":/usr/local/proxy/bin

# Prepend $TERRATEAM_PREPEND_PATH to $PATH
if [ "$TERRATEAM_PREPEND_PATH" ]; then
  export PATH="$TERRATEAM_PREPEND_PATH:$PATH"
fi

# Append $TERRATEAM_APPEND_PATH to $PATH
if [ "$TERRATEAM_APPEND_PATH" ]; then
  export PATH="$PATH:$TERRATEAM_APPEND_PATH"
fi

# Set PATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Adding /usr/local/proxy/bin to the PATH for accessing additional tools, if needed
export PATH="$PATH":/usr/local/proxy/bin

# Prepend $TERRATEAM_PREPEND_PATH to $PATH
if [ "$TERRATEAM_PREPEND_PATH" ]; then
  export PATH="$TERRATEAM_PREPEND_PATH:$PATH"
fi

# Append $TERRATEAM_APPEND_PATH to $PATH
if [ "$TERRATEAM_APPEND_PATH" ]; then
  export PATH="$PATH:$TERRATEAM_APPEND_PATH"
fi

export TENV_AUTO_INSTALL=true

if [ "$TERRAT_VCS_PROVIDER" = "gitlab" ]; then
   /entrypoint_gitlab.sh
else
    /entrypoint_github.sh "$1" "$2"
fi
