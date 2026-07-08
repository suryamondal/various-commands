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
# Keep this "no" even though this option allows password login: the password
# is collected by PAM (pam_unix) through keyboard-interactive, not by SSH's
# own "password" method. Setting it to "yes" would let password-only logins
# bypass TOTP entirely.
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

Notes on this PAM stack:
- **Every user in `AllowUsers` must run `google-authenticator` before sshd is restarted.** Without a `~/.google_authenticator` file, `pam_google_authenticator.so` fails and that user is locked out. For a migration window you can append `nullok` to its line (`auth required pam_google_authenticator.so nullok`), but remember that means un-enrolled users log in with *no second factor* — remove it once everyone is enrolled.
- A wrong password still prompts for a verification code and only fails at the end. That is normal `required` PAM behaviour (it avoids leaking which factor was wrong), not a broken setup.

Create the helper script `/usr/local/bin/check_ssh_auth.sh`:
```BASH
#!/bin/bash

# Debug log (optional): this file is root-owned, never rotated, and the
# script prints nothing by default. Drop these two lines once things work.
exec 1>>/var/log/pam_exec.log 2>&1

# If SSH public key authentication succeeded
if [[ -n "$SSH_AUTH_INFO_0" && "$SSH_AUTH_INFO_0" =~ "publickey" ]]; then
    exit 0
fi

exit 1
```

Install it root-owned and executable — do not just `chmod +x` a file lying in your home directory:
```BASH
sudo install -m 755 -o root -g root check_ssh_auth.sh /usr/local/bin/check_ssh_auth.sh
```
Two failure modes to be aware of:
- If the script is missing or not executable, `pam_exec` fails and `default=ignore` silently falls through to the password line — key users start getting password+TOTP prompts with no error anywhere. That symptom means: check the script.
- The script runs as root during authentication, so it must be writable by root only. A user-writable script here is a privilege escalation.

Install google authenticator and register TOTP app (**for every allowed user, before restarting sshd**).
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
