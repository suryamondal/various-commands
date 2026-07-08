# SSH with F2A

There are two options:




## Publickey + Google TOTP (Safest option)

> Deployed on this machine (user `surya`) on 2026-07-08.

Before starting, make sure your public key is already in `~/.ssh/authorized_keys` — with this config there is **no password fallback**, so a missing key means lockout.

Edit the following file `/etc/ssh/sshd_config.d/00-hardening.conf`.
```BASH
# Use only SSH Protocol 2
Protocol 2

# Allow X11 forwarding (needs xauth installed; connect with ssh -X)
X11Forwarding yes

# Authentication Hardening
MaxAuthTries 5
MaxSessions 25
PermitRootLogin no
PermitEmptyPasswords no
HostBasedAuthentication no
ChallengeResponseAuthentication yes
PasswordAuthentication no
PubkeyAuthentication yes
UsePAM yes
AuthenticationMethods publickey,keyboard-interactive

# Restrict SSH access to specific users (use your actual username)
AllowUsers surya

# Logging
LogLevel VERBOSE
```

Above file is included in `/etc/ssh/sshd_config`. Check that the following line already exists in it (it must come *before* any `KbdInteractiveAuthentication no` in the main file — the first value sshd reads wins).
```BASH
Include /etc/ssh/sshd_config.d/*.conf
```

Back up the PAM config first, then replace the `auth` section of `/etc/pam.d/sshd` with the following (keep the account/session/password sections as they are).
```BASH
sudo cp -a /etc/pam.d/sshd /etc/pam.d/sshd.bak-totp
```
```BASH
# PAM configuration for the Secure Shell service
auth required pam_google_authenticator.so

# # Standard Un*x authentication.
# @include common-auth
```
Make sure to comment out `common-auth` mentioned anywhere, otherwise it will ask for password again.

Install google authenticator and register TOTP app. **Do this before restarting sshd**, otherwise you lock yourself out.
```BASH
sudo apt install libpam-google-authenticator
google-authenticator -t -d -f -r 3 -R 30 -w 3
```
(The flags set up TOTP non-interactively: disallow code reuse, rate-limit to 3 tries per 30 s, window of 3 codes. Scan the QR code with your app and **save the emergency scratch codes**.)

Check the clock is in sync (TOTP needs accurate time).
```BASH
timedatectl    # "System clock synchronized: yes"
# or on older setups:
sudo ntpdate ntp.tifr.res.in
```

Validate the config, then restart `sshd`. On Ubuntu, `ssh` and `sshd` are the same service — restarting `ssh` is enough.
```BASH
sudo sshd -t && sudo systemctl restart ssh
```

**Test from a NEW terminal before closing your current session**: `ssh <user>@<host>` should accept your key and then ask `Verification code:` (the 6-digit TOTP). If something breaks, roll back with:
```BASH
sudo rm /etc/ssh/sshd_config.d/00-hardening.conf
sudo cp /etc/pam.d/sshd.bak-totp /etc/pam.d/sshd
sudo systemctl restart ssh
```






## Publickey / Password + Google TOTP

Edit the following file `/etc/ssh/sshd_config.d/00-hardening.conf`.
```BASH
# Use only SSH Protocol 2
Protocol 2

# Disable X11 forwarding
X11Forwarding no

# Authentication Hardening
MaxAuthTries 5
MaxSessions 4
PermitRootLogin no
PermitEmptyPasswords no
HostBasedAuthentication no
ChallengeResponseAuthentication yes
PasswordAuthentication no
PubkeyAuthentication yes
UsePAM yes
AuthenticationMethods publickey,keyboard-interactive keyboard-interactive

# Restrict SSH access to specific users
AllowUsers mondal ehep24

# Logging
LogLevel VERBOSE
```

Above file is included in `/etc/ssh/sshd_config`. Check if the following line already exists in it.
```BASH
Include /etc/ssh/sshd_config.d/*.conf
```

Include the following in the `/etc/pam.d/sshd` file.
```BASH
# PAM configuration for the Secure Shell service
auth [success=1 default=ignore] pam_exec.so quiet /usr/local/bin/check_ssh_auth.sh
auth required pam_unix.so
auth required pam_google_authenticator.so

# # Standard Un*x authentication.
# @include common-auth
```
Make sure to comment out `common-auth` mentioned anywhere, otherwise it will ask for password again.

Create a file `/usr/local/bin/check_ssh_auth.sh` with the following content and make it executable.
```BASH
#!/bin/bash

# Log debugging information
exec 1>>/var/log/pam_exec.log 2>&1

# If SSH public key authentication succeeded
if [[ -n "$SSH_AUTH_INFO_0" && "$SSH_AUTH_INFO_0" =~ "publickey" ]]; then
    exit 0
fi

exit 1
```

Install google authenticator and register TOTP app.
```BASH
sudo apt install libpam-google-authenticator
google-authenticator
```

Update time. If any error message then stop other time-keepers.
```BASH
sudo ntpdate ntp.tifr.res.in
```

Restart `sshd` using the following.
```BASH
sudo systemctl restart ssh && sudo systemctl restart sshd
```

## Clear Fail2ban
```BASH
sudo fail2ban-client status sshd
sudo fail2ban-client set sshd unbanip <target-ip>
```
