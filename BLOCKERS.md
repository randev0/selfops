# Phase 2 Blocker — k3s Cannot Start

## What Failed

Phase 2 requires k3s to run. The k3s binary is already present at `/home/selfops/bin/k3s` (v1.28.6+k3s2). However, k3s refuses to start because:

```
level=fatal msg="expected sysctl value \"net.ipv4.ip_forward\" to be \"1\", got \"0\";
try adding \"net.ipv4.ip_forward=1\" to /etc/sysctl.conf and running `sudo sysctl --system`"
```

## Root Cause

`net.ipv4.ip_forward` is currently `0` on this server. This kernel setting controls whether the OS can forward IP packets between network interfaces, which is required by every Kubernetes networking implementation (including k3s's default flannel CNI).

This setting requires root to change. The `selfops` user does not have passwordless sudo access.

## What Was Tried

1. Running `k3s server --rootless` — fails with the same sysctl error
2. Running `k3s server --rootless --disable-network-policy` — same error, check happens before CNI
3. Setting ip_forward inside a `unshare --user --net` namespace — the sysctl returns success but the value in `/proc/sys/net/ipv4/ip_forward` stays 0; k3s still rejects it
4. Looking for a k3s environment variable or flag to skip the sysctl check — none found

## How to Fix

A user with root access must run **one of the following** on the server:

### Option A — Permanent (survives reboots, recommended)
```bash
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Option B — Temporary (lost on reboot)
```bash
sudo sysctl -w net.ipv4.ip_forward=1
```

After either option, verify with:
```bash
cat /proc/sys/net/ipv4/ip_forward
# Should print: 1
```

Then resume Phase 2 by telling Claude Code to continue.

## Additional Note

If you also want k3s to start automatically on boot (which this project needs for a production-style setup), you should also run the install script as root after fixing the sysctl:

```bash
sudo INSTALL_K3S_BIN_DIR=/usr/local/bin curl -sfL https://get.k3s.io | sh -
```

Or if you want to register the pre-existing binary as a service:
```bash
sudo INSTALL_K3S_SKIP_DOWNLOAD=true curl -sfL https://get.k3s.io | sh -
```
