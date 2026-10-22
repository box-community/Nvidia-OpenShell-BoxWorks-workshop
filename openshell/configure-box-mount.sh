#!/bin/sh
# Runs inside the sandbox. Writes Box Mount's config with OpenShell's token placeholder, never a real token.
set -eu
case "${BOX_ACCESS_TOKEN:-}" in
    openshell:resolve:env:*) ;;
    *) echo 'Expected an OpenShell token placeholder; no configuration written.' >&2; exit 1 ;;
esac
umask 077
mkdir -p /sandbox/.box-mount
printf '{"auth_type":"oauth","client_id":"host-managed","client_secret":"unused","access_token":"%s","refresh_token":"unused"}\n' "$BOX_ACCESS_TOKEN" > /sandbox/.box-mount/box-config.json
echo 'Configured Box Mount with an OpenShell placeholder, not a real token.'
