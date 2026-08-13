# FileUploader

A small Linux desktop app for handing someone a file without handing them a
permanent copy. Pick a file, get a short link, send it. The link dies on its own.

```
┌────────────────────────────────────────┐
│  FILE·UPLOADER               Saved text│
├────────────────────────────────────────┤
│   ┌────────────┬────────────┐          │
│   │    File    │    Text    │          │
│   └────────────┴────────────┘          │
│   ╔══════════════════════════════════╗ │
│   ║        Choose a file             ║ │
│   ║        or drop one here          ║ │
│   ╚══════════════════════════════════╝ │
│   VANISHES AFTER                       │
│   ──────●───────────────○──────        │
│      3 hours          3 days           │
│      up to 4 GB · stored on temp.sh    │
│   CUSTOM LINK — OPTIONAL               │
│   ulvis.net/ [ holidayphotos         ] │
│   [           Get link              ]  │
└────────────────────────────────────────┘
```

## Install

One file, whichever system you are on. Python and everything else is already
inside it — there is nothing to install alongside it.

| System | File | Size |
|---|---|---|
| Windows 10 / 11, 64-bit | [`fileuploader.exe`](https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/fileuploader.exe) | 18 MB |
| Linux, 64-bit | [`fileuploader`](https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/fileuploader) | 48 MB |

### Windows

Download **[fileuploader.exe](https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/fileuploader.exe)**
and double-click it. That is the whole install.

The first launch shows **"Windows protected your PC"** — the blue box. It is not
a virus warning: it means the file has no code-signing certificate, which costs
a few hundred a year. Click **More info**, then **Run anyway**. Windows asks
once and remembers.

To keep it: move the `.exe` somewhere permanent — `Documents\Apps` is fine —
then right-click it and choose **Pin to Start**.

Or from PowerShell:

```powershell
curl.exe -L -o fileuploader.exe https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/fileuploader.exe
.\fileuploader.exe
```

Nothing else is needed. The window is drawn by WebView2, which ships with
Windows 11 and reached Windows 10 through Edge updates. On a machine without it,
the app opens in your browser instead of its own window.

### Linux

```bash
curl -L -o fileuploader https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/fileuploader
chmod +x fileuploader
./fileuploader
```

To add it to your applications menu:

```bash
curl -L -o install.sh https://github.com/Abdullah-Handal/FileUploader/raw/master/install.sh
bash install.sh ./fileuploader
```

One thing is not inside the file, because every Linux desktop already has it:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1     # Debian, Ubuntu, Mint
sudo dnf install python3-gobject webkit2gtk4.1     # Fedora
sudo pacman -S python-gobject webkit2gtk-4.1       # Arch
```

That is WebKit, which draws the window. Without it the app still works — it
opens in your browser instead.

## What it does

- **Share a file.** Native file picker, or drop a file onto the window.
- **Share text.** Paste something, name it, and it becomes a `.txt` you can send.
  The text file is kept on your machine after the link expires.
- **Choose how long it lives.** The lifetime picks the host, because that is the
  only thing you actually care about.
- **Name your own link.** Optional. Blank gives you a random one.

## Building it yourself

### Running from source

```bash
./run.sh
```

First run creates the virtualenv and installs dependencies; after that it just
starts. Add `--browser` to open in your browser instead of a native window.

### Making the executable

```bash
./build.sh              # one self-contained file -> dist/fileuploader  (~48 MB)
./build.sh --folder     # a folder that starts faster -> dist/fileuploader/
./install.sh            # add it to your applications menu
```

`install.sh` also takes a path, so it works on a downloaded executable that was
never built here: `./install.sh ~/Downloads/fileuploader`.

On Windows, `build.bat` does the same thing. You will rarely need it: pushing a
`v*` tag builds the `.exe` on a GitHub Actions runner and attaches it to the
release, and the Actions tab can run that build on demand. PyInstaller cannot
cross-compile, so a Windows executable has to be built on Windows — the runner
is there so you do not need a Windows machine of your own.

The build bundles Python, the server and the interface. It does **not** bundle
GTK's icon and theme artwork — over 29,000 files that GTK reads from the system
anyway, and which would otherwise triple the size.

### Requirements

Python 3.11+, plus the WebKit packages from the Download section above.

PyGObject is deliberately not in `requirements.txt`. Building it from source
needs cairo and girepository development headers, and every Linux desktop ships
a working copy — so the virtualenv is created with `--system-site-packages` and
uses that one.

## Where things go

| What | Linux | Windows |
|---|---|---|
| Text snippets you shared | `~/.local/share/fileuploader/texts/` | `%LOCALAPPDATA%\fileuploader\texts\` |
| Recent links | `~/.local/share/fileuploader/history.json` | `%LOCALAPPDATA%\fileuploader\history.json` |

Files you pick are **never copied** — only read and uploaded. Dropped files are
copied to a temporary directory and deleted afterwards, because a webview hands
over the file's contents rather than its path.

## Hosts

Both were verified by uploading a file and downloading it again byte-for-byte.

| Lifetime | Host | Max size | Link |
|---|---|---|---|
| 3 hours | uguu.se | 128 MB | serves the file directly |
| 3 days | temp.sh | 4 GB | opens a page with a download button |

Links can be downloaded as many times as you like while they last.

**Why not Litterbox?** It is the obvious choice — selectable 1h/12h/24h/72h
windows and 1 GB — and it was the original plan. Its upload endpoint answers
HTTP 412 `No file!` to a correctly formed request, including the exact `curl`
command in its own documentation, and including with a session cookie.
catbox.moe, its sibling service, accepts the identical request shape, so this is
Litterbox refusing rather than a bug here.

## Short links

Two keyless providers, tried in order:

1. **ulvis.net** — honours custom names, reports collisions clearly, no rate limiting observed.
2. **is.gd** — fallback. It answers `Error, database insert failed` to valid
   requests after a handful in quick succession, so it cannot be relied on alone.

If both refuse, you keep the host's own URL. It is longer, but it works.

Custom names are limited to **5–30 letters and numbers**. Nothing else, because
ulvis silently strips other characters — ask for `my-file` and you get `myfile`,
and a link that isn't the one you typed is worse than being asked to retype it.

If your name is taken, the app says so and lets you pick another **without
re-uploading** the file.

## How it is put together

```
desktop.py        opens a native window over the local server
  server/main.py  the HTTP API, and serves the interface
  app/hosts.py    the upload hosts and the lifetimes they back
  app/shortener.py  ulvis.net, then is.gd
  app/uploader.py   runs one share on a background thread
  app/paths.py      where things live, in source and once frozen
  web/index.html    the whole interface, one file

.github/workflows/windows.yml   builds the .exe on a Windows runner
```

The server binds a random loopback port and the webview points at it. Uploads
stream, so a 4 GB file never lands in memory.
