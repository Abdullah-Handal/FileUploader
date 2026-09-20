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

Python and everything else is already inside — there is nothing to install
alongside it.

| System | File | Size |
|---|---|---|
| Windows 10 / 11, 64-bit | [`FileUploader-windows.zip`](https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/FileUploader-windows.zip) | 18 MB |
| Linux, 64-bit | [`fileuploader`](https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/fileuploader) | 48 MB |

### Windows

Download **[FileUploader-windows.zip](https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/FileUploader-windows.zip)**,
right-click it, choose **Extract All**, and run **`fileuploader.exe`** from the
folder that appears. That is the whole install.

Extract it before running. Opening the zip in Explorer and double-clicking the
`.exe` inside runs it from a temporary folder without the `window\` beside it,
and it will fall back to your browser.

The folder holds two programs, and only the first is yours to click:

```
fileuploader.exe               <- this one          15 MB
window\FileUploaderWindow.exe   <- started by it     9 MB
```

`fileuploader.exe` is the server and everything that uploads. The one beside it
is the window, and nothing else — it is started for you and closes with the app.
24 MB once extracted.

The first launch shows **"Windows protected your PC"** — the blue box. It is not
a virus warning: it means the file has no code-signing certificate, which costs
a few hundred a year. Click **More info**, then **Run anyway**. Windows asks
once and remembers.

To keep it: move the folder somewhere permanent — `Documents\Apps` is fine —
then right-click `fileuploader.exe` and choose **Pin to Start**.

Or from PowerShell:

```powershell
curl.exe -L -o FileUploader-windows.zip https://github.com/Abdullah-Handal/FileUploader/releases/latest/download/FileUploader-windows.zip
Expand-Archive FileUploader-windows.zip -DestinationPath FileUploader
.\FileUploader\fileuploader.exe
```

The window is drawn by WebView2, which ships with Windows 11 and reached
Windows 10 through Edge updates. On a machine without it, the app says so and
opens in your browser instead.

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

On Windows there are two halves, and a runner builds both. Pushing a `v*` tag
produces `FileUploader-windows.zip` and attaches it to the release; the Actions
tab can run that build on demand. Neither PyInstaller nor Tauri cross-compiles,
so this has to happen on Windows — the runner is there so you do not need a
Windows machine of your own.

The window on Windows is **[Pake](https://github.com/tw93/Pake)**, which wraps a
page in a Tauri (Rust) shell around the system WebView2. It replaced pywebview,
which reaches WebView2 through pythonnet: that opened a window and then never
painted the page into it, which is the blank window this fixes. Pake draws only
the window — the server, the uploading and the history are the same Python as
everywhere else, which is why the download is a folder rather than one file.

`pake.json` holds the window's settings. It bakes its URL in at build time, so
the port there and `SHELL_PORT` in `desktop.py` both say `8765` and have to keep
saying the same thing. `fileuploader.exe` binds that port, starts the window
beside it, and shuts the server down when the window closes. With no window
found, no WebView2 installed, or a window that fails to come up, it falls back
to the browser and says so.

`build.bat` still builds the Python half alone, which is all you need to test
the server.

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
desktop.py        serves the app and opens a window over it
  server/main.py  the HTTP API, and serves the interface
  app/hosts.py    the upload hosts and the lifetimes they back
  app/shortener.py  ulvis.net, then is.gd
  app/uploader.py   runs one share on a background thread
  app/paths.py      where things live, in source and once frozen
  app/shell.py      hands links and folders to the desktop
  web/index.html    the whole interface, one file

pake.json         the Windows window: a Pake/Tauri shell over WebView2
assets/icon.png   the mark Pake turns into the .ico

.github/workflows/windows.yml   builds both Windows halves on a runner
```

Uploads stream, so a 4 GB file never lands in memory.

The server binds a loopback port and the window points at it. On Linux that is
a random port, because pywebview is told where to look. On Windows it is 8765,
because a Tauri shell is compiled against one URL and cannot be told another —
if something else already holds 8765, the app opens in your browser instead.
