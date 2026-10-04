# sushantgautam/open-webui — subpath build of Open WebUI

Fork of [open-webui/open-webui](https://github.com/open-webui/open-webui)
that can be served under a **URL subpath** (e.g. `/chat`) behind a reverse
proxy, instead of only at the origin root. Used by SimpleAudit Studio to
embed chat at `https://studio.example.com/chat/`.

Upstream rejected subpath support as a feature (open-webui/open-webui#10440,
#23242) — maintain a small downstream patch instead, per the maintainers'
suggestion.

## What the subpath commits change (121 files)

- **Backend**: `FastAPI(root_path=WEBUI_SUBPATH)`, `uvicorn.run(root_path=...)`
  (serve + dev), `socketio_path=f'{WEBUI_SUBPATH}/ws/socket.io'`, redirect
  targets, config/manifest/swagger asset paths all respect `WEBUI_SUBPATH`.
- **Frontend**: SvelteKit `paths.base` + `relative: false`, Vite `base`,
  `WEBUI_BASE_URL = base` (single API choke point), and all `goto()`/`href`/
  `location.href` internal routes prefixed.
- **Dockerfile**: `WEBUI_SUBPATH` as a build **and** runtime arg.
- Plus: `NODE_OPTIONS=--max-old-space-size=6144` so the SvelteKit build
  doesn't OOM on constrained builders.

**The subpath is baked at build time** into the JS — one image = one subpath.
A `/chat` image cannot be served at `/helpdesk` without rebuilding.

## Building

### CI (published to ghcr.io)

Workflow `Create and publish Docker images with specific build args`
(`.github/workflows/docker.yaml`):
- auto-runs on `main` pushes and `v*` tags
- manual trigger: **Actions → workflow → Run workflow** with
  `webui_subpath = /chat`

Images (per ref, per arch amd64/arm64):
- `ghcr.io/sushantgautam/open-webui:<tag>`            (root; auto)
- `ghcr.io/sushantgautam/open-webui:<tag>-subpath`    (manual, subpath baked)
  e.g. `ghcr.io/sushantgautam/open-webui:v0.9.6-subpath`
- Variants: `-cuda`, `-cuda126`, `-ollama`, `-slim` suffixes as upstream.

### Local

```bash
git clone https://github.com/sushantgautam/open-webui && cd open-webui
docker build --build-arg WEBUI_SUBPATH=/chat -t open-webui-subpath:chat .
```

## Serving behind a proxy

The proxy must forward **without stripping** the prefix (the app generates
all public URLs including the prefix; engine.io matches the raw path):

```
/chat/* → open-webui:8080   (no strip)
```

Reference: SimpleAudit Studio `deploy/openwebui-subpath/Caddyfile.subpath`.

## Upgrading to a new upstream version

Base pinned: upstream `02dc3e689` (v0.9.6 generation, "Merge PR #25590").

Procedure (see SimpleAudit Studio `deploy/openwebui-subpath/UPGRADE.md` for
the full agent prompt + evidence bar):

```
1. git remote add upstream https://github.com/open-webui/open-webui
2. git fetch upstream <new-tag>
3. git rebase upstream/<new-tag>          # replay the 2 subpath commits
4. WEBUI_SUBPATH=/chat npm run build      # frontend compiles?
5. docker build + smoke: /chat/health, 0 unprefixed SPA refs,
   WS /chat/ws/socket.io → 101, one LLM round-trip
6. git tag v<new>-subpath  (CI publishes)
```

Measured drift at v0.11.4: 33/121 files clean, 88 with conflicts (8 of the
9 core files). Treat a bump as a **porting task**, not a re-apply. Do not
promote a version until the smoke bar passes.

## License

MIT — same as upstream. Fork of open-webui/open-webui.
