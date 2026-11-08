# Running the Portkey gateway (loopback only)

Tested 2026-11-08 on Windows 11, PowerShell, Node 22.22.0, @portkey-ai/gateway 1.15.2. Run from the repo root: the preload path is relative.

The gateway has no `--host` option and listens on all interfaces without the preload. Never start it without `routers/configs/portkey_loopback.cjs`.

## Start

`npx` exited 1 with no output in two runs on this machine (cause not found):

```powershell
$env:NODE_OPTIONS='--require=./routers/configs/portkey_loopback.cjs'; npx -y @portkey-ai/gateway@1.15.2 --port=8787 --headless
```

This is the command that worked. It runs the build `npx` cached earlier. The `548a07a06b2635c0` folder name is specific to this machine; find yours under `%LOCALAPPDATA%\npm-cache\_npx\`.

```powershell
$env:NODE_OPTIONS='--require=./routers/configs/portkey_loopback.cjs'; node "$env:LOCALAPPDATA\npm-cache\_npx\548a07a06b2635c0\node_modules\@portkey-ai\gateway\build\start-server.js" --port=8787 --headless
```

## Check the binding

Expect `127.0.0.1` only:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8787 | Select-Object LocalAddress,LocalPort,OwningProcess
```

## Stop

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8787 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Mock provider, for the same runs

```powershell
.\.venv\Scripts\python.exe -m uvicorn mock_provider.app:app --host 127.0.0.1 --port 8900 --log-level warning
```

Stop it the same way, with port 8900.
