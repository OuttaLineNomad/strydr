# Installing Strydr on Windows

For Windows 10 (version 22H2) and Windows 11, 64-bit, signed in with an administrator account.
Virtualization must be on in the BIOS (it usually is; the installer says if not). The PC needs about 10 GB free and an
internet connection, and it should stay on at home so your iPhone can sync to it.

## Install

1. Download [Install Strydr.cmd](https://raw.githubusercontent.com/OuttaLineNomad/strydr/main/install/windows/Install%20Strydr.cmd)
   (right-click the link, **Save link as**, keep the `.cmd` name).
2. Double-click it. If Windows says it protected your PC, click **More info**, then **Run anyway**.
3. Click **Yes** when Windows asks for administrator rights.
4. Wait. The first install takes 15 to 40 minutes. It turns on WSL 2, installs Docker Desktop, and
   restarts the PC once. After the restart, sign in. The installer carries on by itself; click **Yes** again.
   If Docker Desktop shows a welcome screen or asks you to sign in, you can skip it.
5. When it finishes, Notepad opens **Strydr details.txt** (also on your Desktop) with:
   - the address of Strydr and a Desktop icon
   - your username and password
   - the URL and token for the Health Auto Export app, with the steps for your iPhone
   - where to find the database key: a copy of the file that includes it is kept in
     `%LOCALAPPDATA%\Strydr`, off the Desktop, because the Desktop may sync to OneDrive

Instead of the `.cmd` file, you can paste this into PowerShell:

```powershell
irm https://raw.githubusercontent.com/OuttaLineNomad/strydr/main/install/windows/install.ps1 | iex
```

## Update

Run the installer again. Your data, password and token stay the same.

## What it changes on the PC

- Turns on the Windows features WSL and Virtual Machine Platform, and installs Docker Desktop.
- Adds your account to the `docker-users` group, and starts Docker Desktop when you sign in.
- Puts Strydr in `%LOCALAPPDATA%\Strydr`. The data lives in a Docker volume named `strydr_strydr_data`.
- Adds a firewall rule named **Strydr** for ports 8080 and 8081 on private networks. If your home network
  is marked Public, it asks before marking it Private.
- Turns off sleep while the PC is plugged in.

## Uninstall

In PowerShell: `cd $env:LOCALAPPDATA\Strydr\app; docker compose down -v`. This deletes all Strydr data.
Then delete the `%LOCALAPPDATA%\Strydr` folder, and uninstall Docker Desktop if nothing else uses it.
