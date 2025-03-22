# SSH Configuration File

The file `~/.ssh/config` contains the required information for the `SSH` to operate smoothly.
This file helps
- to establish `ssh` or `rsync` without typing password every time
- to establish `ssh` or `rsync` from `A` to `B` via `A->C->D->B` in one step
- to `push or pull` from a remote repository

Check all, then write your own `config` file. A sample `config` file also can be found in this
repository.

## The contents of `config`
### Keeping `ssh` alive for long time

*Is you `ssh` keep failing when kept idle for long??* The solution is here.

Add the following in the `~/.ssh/config` file.
```
ServerAliveInterval 60
```

### Establish `ssh` to a `public` terminal:

The following piece of code goes in the `~/.ssh/config` file.
```
Host remote1
     User myusername
     Hostname host.public.ip.or.url
     IdentityFile ~/.ssh/id_rsa_remote1
```

The point of all of this is that one can just `ssh remote1`, instead of `ssh myusername@host.public.ip.or.url`.

Now the ` ~/.ssh/id_rsa_remote1` file needed to be created.

In simple, a pair of `public` and `private` keys are created. The `public` key is then copied to the `remote1` terminal.

Execute the following in a terminal to generate the key,
```
ssh-keygen -C "my_laptop"
```
Give the `path/to/file` as `/home/username/.ssh/id_rsa_remote1`. **Give the full name. It does not resolve `~`.**

*Note*: Never keep the passphrase empty. Keep it different than the `ssh user password`.

Now, copy the `public` key to the `remote1` using the following command.
```
ssh-copy-id -i ~/.ssh/id_rsa_remote1 remote1
```
It may ask user password multiple times, don't worry.

After this, whenever you do `ssh` to `remote1`, it should not ask for ssh user password. You need to provide the `ssh passphrase` once after rebooting the terminal.

### Establish `ssh` to a `private` terminal via `public` terminal:
*local->remote1->remote2*

Add the following piece of code in the `~/.ssh/config` file.
```
Host remote2
     User myotherusername
     Hostname host.private.ip.or.url
     IdentityFile ~/.ssh/id_rsa_remote2
     ProxyJump remote1
```

The `ProxyJump` does all the magic.

Generate the key in the same way, only change the path to `~/.ssh/id_rsa_remote2`.

Then, copy the `public` key to the `remote2` using the following key.
```
ssh-copy-id -i ~/.ssh/id_rsa_remote2 remote2
```

It is now done. Do `ssh remote2` or `rsync remote2:/home/myusername/path/to/file .` No need to do it in multiple stages.

### For [GitHub](github.com) ( or [GitLab](gitlab.com) or [BitBucket](bitbucket.org))

Add the following piece of code in the `~/.ssh/config` file.
```
Host github.com
     User git
     IdentityFile ~/.ssh/id_rsa_github
```

Note the `user` in this case, it is not the github `username`. Now,
- Generate the `id_rsa_github` in the same way described above.
- Copy the content (the `public key`) of `id_rsa_github.pub`. Go to the `Settings->SSH Keys->New SSH Keys` and paste it there.
- Last word of the `public key` is the `name` of the key (i.e. `my_laptop`). If you keep the `title` field empty, github would automatically take the `name`.
- Test the connection now by using `ssh -T git@github.com`.

### If Bitbucket returns the following after an update to OpenSSH 8.8:
```
Unable to negotiate with <ip address> port <port number>: no matching host key type found. Their offer: ssh-rsa,ssh-dss
```
then add the following in the `config` file following `IdentityFile ....`.
```
     HostKeyAlgorithms +ssh-rsa
     PubkeyAcceptedKeyTypes +ssh-rsa
```

All set, you may now do `push` or `pull` without any headache.


## Extra: if you need to access internet via the host

Execute the following in a terminal to create `SOCKS` tunnel through `SSH`. This is also called dynamic port forwarding.
```
ssh -N -D 9050 remote1
```

Then in the browser, change the SOCKS settings to the following
```
SOCKS host : 127.0.0.1 port : 9050 SOCKSv5
```

Now internet should work through `SSH`.
