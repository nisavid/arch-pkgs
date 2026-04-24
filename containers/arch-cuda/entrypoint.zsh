#!/usr/bin/env zsh
set -euo pipefail

if [[ -z "${PUBLIC_KEY:-}" ]]; then
  print -u2 "PUBLIC_KEY is required for SSH access."
  exit 64
fi

install -d -m 700 /root/.ssh
print -r -- "${PUBLIC_KEY}" > /root/.ssh/authorized_keys
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys

if ! ssh-keygen -l -f /root/.ssh/authorized_keys >/dev/null; then
  print -u2 "PUBLIC_KEY is not a valid SSH public key."
  exit 64
fi

install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config <<'EOF'
Port 22
Protocol 2
HostKey /etc/ssh/ssh_host_rsa_key
HostKey /etc/ssh/ssh_host_ecdsa_key
HostKey /etc/ssh/ssh_host_ed25519_key
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
UsePAM no
AllowTcpForwarding yes
X11Forwarding no
Subsystem sftp /usr/lib/ssh/sftp-server
EOF

ssh-keygen -A
exec /usr/sbin/sshd -D -e
