# SSH with F2A

There are two options:




## Publickey + Google TOTP (Safest option)

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
AuthenticationMethods publickey,keyboard-interactive

# Restrict SSH access to specific users
AllowUsers mondal

# Logging
LogLevel VERBOSE
```

Above file is file is included in `/etc/ssh/sshd_config`. Check if the following command already exists in it.
```BASH
Include /etc/ssh/sshd_config.d/*.conf
```

Include the following in the `/etc/pam.d/sshd` file.
```BASH
# PAM configuration for the Secure Shell service
auth required pam_google_authenticator.so

# # Standard Un*x authentication.
# @include common-auth
```
Make sure to comment out `common-auth` mentioned anywhere, otherwise it will ask for password again.

Install google authenticator and register TOTP app.
```BASH
sudo apt install libpam-google-authenticator
google-authenticator
```

Update time. If any error messege then stop other time-keepers.
```BASH
sudo ntpdate ntp.tifr.res.in
```

Restart `sshd` using the following.
```BASH
sudo systemctl restart ssh && sudo systemctl restart sshd
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

Above file is file is included in `/etc/ssh/sshd_config`. Check if the following command already exists in it.
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

# Log debugging informationsudo systemctl restart ssh && sudo systemctl restart ssh
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

Update time. If any error messege then stop other time-keepers.
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
