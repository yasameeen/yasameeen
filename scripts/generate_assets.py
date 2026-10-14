#!/usr/bin/env python3
"""
Gera os SVGs dinâmicos do perfil (assets/numeros.svg e assets/atividade.svg) a
partir da API do GitHub. O workflow .github/workflows/refresh-assets.yml roda
isso 1x por dia e commita o resultado — os SVGs do README nunca envelhecem.

Uso:
    python3 scripts/generate_assets.py                          # dados públicos (padrão)
    python3 scripts/generate_assets.py --with-private-metrics    # inclui PRs de repos privados
    python3 scripts/generate_assets.py --user yasameeen --out assets

Privacidade: por padrão as métricas de PR/issue vêm da busca SEM autenticação,
ou seja, só o que é público. O número fica igual rodando na tua máquina e no CI,
e não revela o volume do teu trabalho privado. O flag --with-private-metrics usa
o GITHUB_TOKEN e passa a contar repos privados também (rode local, revise o SVG
gerado e commite se quiser expor esses números).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.github.com"
MONO = "ui-monospace,SFMono-Regular,'JetBrains Mono',Menlo,Consolas,monospace"
SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,'Times New Roman',serif"

LANG_COLORS = {
    "Java": "#b07219", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Python": "#3572A5",
    "Shell": "#89e051", "HTML": "#e34c26", "CSS": "#563d7c", "Vue": "#41b883", "C#": "#178600",
    "Go": "#00ADD8", "Rust": "#dea584", "Kotlin": "#A97BFF", "Dart": "#00B4AB", "C++": "#f34b7d",
    "C": "#555555", "Ruby": "#701516", "PHP": "#4F5D95", "SCSS": "#c6538c", "EJS": "#a91e50",
    "Batchfile": "#C1F12E", "Jupyter Notebook": "#DA5B0B", "Dockerfile": "#384d54",
}


def _get(path: str, token: str | None = None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "grimorio-profile-assets"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def gh(path: str, token: str | None = None):
    return _get(path, token)


def search_count(q: str, token: str | None = None) -> int:
    """Conta PRs/issues. Sem token = só o que é público (comportamento padrão)."""
    try:
        data = _get(f"/search/issues?q={urllib.parse.quote(q)}&per_page=1", token)
        return int(data.get("total_count", 0))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! busca falhou ({q}): {exc}", file=sys.stderr)
        return 0


def fetch_events(user: str, token: str | None) -> list[dict]:
    """Eventos públicos na janela que a API guarda (~90 dias, até 3 páginas)."""
    events: list[dict] = []
    for page in (1, 2, 3):
        try:
            batch = gh(f"/users/{user}/events/public?per_page=100&page={page}", token)
        except urllib.error.HTTPError as exc:
            print(f"  ! eventos página {page}: {exc.code}", file=sys.stderr)
            break
        if not batch:
            break
        events.extend(batch)
        oldest = batch[-1].get("created_at", "")
        if oldest:
            try:
                if (datetime.now(timezone.utc) - datetime.fromisoformat(oldest.replace("Z", "+00:00"))).days > 21:
                    break
            except ValueError:
                pass
    return events


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# --------------------------------------------------------------------------- #
# numeros.svg — painel 4x2 de números reais
# --------------------------------------------------------------------------- #
def svg_numbers(user: dict, repos: list[dict], token: str | None, private_metrics: bool) -> str:
    login = user.get("login", "yasameeen")
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    langs: dict[str, int] = {}
    for r in repos:
        if r.get("language"):
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:5]
    since = (user.get("created_at") or "")[:4]
    years = (datetime.now(timezone.utc).year - int(since)) if since.isdigit() else 0

    last_push = max((r.get("pushed_at") or "" for r in repos), default="")[:10]
    try:
        last_push_br = datetime.fromisoformat(last_push).strftime("%d/%m/%y") if last_push else "—"
    except ValueError:
        last_push_br = last_push or "—"

    tok = token if private_metrics else None
    prs = search_count(f"author:{login} type:pr", tok)
    merged = search_count(f"author:{login} type:pr is:merged", tok)
    issues = search_count(f"author:{login} type:issue", tok)

    blocks = [
        ("repositórios públicos", str(user.get("public_repos", len(repos)))),
        ("seguidores", str(user.get("followers", 0))),
        ("estrelas recebidas", str(stars)),
        ("linguagens no código", str(len(langs))),
        ("pull requests" + ("" if private_metrics else " públicas"), str(prs)),
        ("prs mergeadas", str(merged)),
        ("issues registradas", str(issues)),
        ("último push", last_push_br),
    ]
    parts = []
    for i, (label, value) in enumerate(blocks):
        col, row = i % 4, i // 4
        x, y = 78 + col * 292, 108 + row * 96
        parts.append(f'''  <g transform="translate({x},{y})">
    <text x="0" y="0" font-family="{SERIF}" font-size="46" fill="#f6c177">{esc(value)}</text>
    <text x="0" y="28" font-family="{MONO}" font-size="13" letter-spacing="2.4" fill="#a99fc9">{esc(label.upper())}</text>
  </g>''')

    total = sum(n for _, n in top) or 1
    bar_x, bar_y, bar_w, bar_h = 78, 322, 1124, 14
    segs, cx = [], bar_x
    for i, (name, n) in enumerate(top):
        w = max(8, (n / total) * bar_w)
        if i == len(top) - 1:
            w = max(8, bar_x + bar_w - cx)
        color = LANG_COLORS.get(name, "#a78bfa")
        segs.append(f'    <rect x="{cx:.1f}" y="{bar_y}" width="{w:.1f}" height="{bar_h}" rx="7" fill="{color}" opacity="0.92">'
                    f'<animate attributeName="opacity" values="0;0.92" dur="1.1s" begin="{0.15*i:.2f}s" fill="freeze"/></rect>')
        cx += w
    legend, lx = [], 78
    for name, n in top:
        color = LANG_COLORS.get(name, "#a78bfa")
        legend.append(f'  <g transform="translate({lx},362)">'
                      f'<circle cx="0" cy="-4" r="4.4" fill="{color}"/>'
                      f'<text x="13" y="0" font-family="{MONO}" font-size="13" fill="#c9c1e6">{esc(name)} '
                      f'<tspan fill="#8b81ad">{n}</tspan></text></g>')
        lx += 46 + len(name) * 8.2
    if not legend:
        legend.append(f'  <text x="78" y="362" font-family="{MONO}" font-size="13" fill="#8b81ad">'
                      f'nenhuma linguagem pública ainda — o trabalho mora nos repos privados</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 400" width="1280" height="400" role="img" aria-label="números do GitHub de {esc(login)}">
  <defs>
    <linearGradient id="nb" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0a0518"/><stop offset="60%" stop-color="#0e0722"/><stop offset="100%" stop-color="#0b0b24"/>
    </linearGradient>
    <radialGradient id="nh" cx="0.12" cy="0.1" r="0.7">
      <stop offset="0%" stop-color="#7c3aed" stop-opacity="0.34"/><stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="nh2" cx="0.9" cy="0.9" r="0.7">
      <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.20"/><stop offset="100%" stop-color="#22d3ee" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="nc"><rect width="1280" height="400" rx="18"/></clipPath>
  </defs>
  <g clip-path="url(#nc)">
    <rect width="1280" height="400" fill="url(#nb)"/>
    <rect width="1280" height="400" fill="url(#nh)"/>
    <rect width="1280" height="400" fill="url(#nh2)"/>
    <g stroke="#a78bfa" stroke-opacity="0.07"><path d="M370 0 V400 M662 0 V400 M954 0 V400 M0 210 H1280"/></g>
    <text x="78" y="52" font-family="{MONO}" font-size="14" letter-spacing="4" fill="#f6c177">✦ NÚMEROS REAIS, COLHIDOS HOJE</text>
    <text x="1202" y="52" font-family="{MONO}" font-size="12.5" letter-spacing="2" fill="#8b81ad" text-anchor="end">gerado {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}</text>
{chr(10).join(parts)}
    <g>{chr(10)}{chr(10).join(segs)}{chr(10)}    </g>
{chr(10).join(legend)}
    <text x="1202" y="362" font-family="{MONO}" font-size="11.5" letter-spacing="2" fill="#8b81ad" text-anchor="end">{esc(user.get('name') or login)} · {years} anos de conta</text>
  </g>
  <rect x="0.5" y="0.5" width="1279" height="399" rx="18" fill="none" stroke="#a78bfa" stroke-opacity="0.26"/>
</svg>
'''


# --------------------------------------------------------------------------- #
# atividade.svg — 14 dias em barras que parecem vela de runa
# --------------------------------------------------------------------------- #
def svg_activity(user: str, events: list[dict]) -> str:
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    counts = {d: 0 for d in days}
    kinds: dict[str, int] = {}
    for e in events:
        try:
            d = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).date()
        except (KeyError, ValueError):
            continue
        name = e.get("type", "?")
        kinds[name] = kinds.get(name, 0) + 1
        if d in counts:
            counts[d] += 1

    peak = max(counts.values()) or 1
    base_y, bw, gap, x0 = 236, 46, 34, 88
    bars = []
    for i, d in enumerate(days):
        v = counts[d]
        h = 10 + (v / peak) * 132
        x = x0 + i * (bw + gap)
        y = base_y - h
        op = "0.95" if v > 0 else "0.28"
        bars.append(f'''    <g>
      <rect x="{x}" y="{y:.1f}" width="{bw}" height="{h:.1f}" rx="9" fill="url(#ag)" opacity="{op}">
        <animate attributeName="height" from="6" to="{h:.1f}" dur="0.9s" begin="{0.06*i:.2f}s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
        <animate attributeName="y" from="{base_y - 6}" to="{y:.1f}" dur="0.9s" begin="{0.06*i:.2f}s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
      </rect>
      <text x="{x + bw / 2:.0f}" y="{base_y + 26}" font-family="{MONO}" font-size="13" fill="#8b81ad" text-anchor="middle">{d.strftime('%d/%m')}</text>''')
        if v > 0:
            bars.append(f'''      <text x="{x + bw / 2:.0f}" y="{y - 12:.1f}" font-family="{MONO}" font-size="13" fill="#fde68a" text-anchor="middle" opacity="0.95">{v}</text>''')
        bars.append("    </g>")

    total = sum(counts.values())
    streak = 0
    for d in reversed(days):
        if counts[d] > 0:
            streak += 1
        else:
            break
    top_kinds = ", ".join(f"{k.replace('Event', '').lower()} {n}" for k, n in
                          sorted(kinds.items(), key=lambda kv: -kv[1])[:4]) or "sem eventos públicos na janela"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 320" width="1280" height="320" role="img" aria-label="atividade pública dos últimos 14 dias de {esc(user)}">
  <defs>
    <linearGradient id="ab" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#08040f"/><stop offset="100%" stop-color="#0d0722"/>
    </linearGradient>
    <linearGradient id="ag" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#4c1d95"/><stop offset="55%" stop-color="#a855f7"/><stop offset="100%" stop-color="#f6c177"/>
    </linearGradient>
    <linearGradient id="al" gradientUnits="userSpaceOnUse" x1="88" y1="240" x2="1192" y2="240">
      <stop offset="0%" stop-color="#a78bfa" stop-opacity="0"/><stop offset="50%" stop-color="#c4b5fd" stop-opacity="0.55"/><stop offset="100%" stop-color="#22d3ee" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="ah" cx="0.5" cy="1.05" r="0.8">
      <stop offset="0%" stop-color="#a855f7" stop-opacity="0.28"/><stop offset="100%" stop-color="#a855f7" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="ac"><rect width="1280" height="320" rx="18"/></clipPath>
  </defs>
  <g clip-path="url(#ac)">
    <rect width="1280" height="320" fill="url(#ab)"/>
    <rect width="1280" height="320" fill="url(#ah)"/>
    <text x="88" y="52" font-family="{MONO}" font-size="14" letter-spacing="4" fill="#f6c177">✦ ATIVIDADE PÚBLICA · ÚLTIMOS 14 DIAS</text>
    <text x="1192" y="52" font-family="{MONO}" font-size="11.5" letter-spacing="2" fill="#8b81ad" text-anchor="end">{esc(user)} · {esc(top_kinds)}</text>
    <path d="M88 240 H1192" stroke="url(#al)" stroke-width="1.4" fill="none"/>
{chr(10).join(bars)}
    <g transform="translate(88,292)" font-family="{MONO}" font-size="13" letter-spacing="2" fill="#c9c1e6">
      <circle cx="0" cy="-4" r="3.6" fill="#f6c177"/><text x="14" y="0">EVENTOS NA JANELA: {total}</text>
      <circle cx="248" cy="-4" r="3.6" fill="#67e8f9"/><text x="262" y="0">DIAS SEGUIDOS COM ATIVIDADE: {streak}</text>
    </g>
  </g>
  <rect x="0.5" y="0.5" width="1279" height="319" rx="18" fill="none" stroke="#a78bfa" stroke-opacity="0.26"/>
</svg>
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  ✓ {path} ({len(content):,} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.environ.get("GH_USER", "yasameeen"))
    ap.add_argument("--out", default="assets")
    ap.add_argument("--with-private-metrics", action="store_true",
                    help="conta PRs/issues de repositórios privados (usa GITHUB_TOKEN)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(f"→ coletando dados de github.com/{args.user} "
          f"({'com token' if token else 'sem token'}; métricas "
          f"{'INCLUINDO privados' if args.with_private_metrics else 'somente públicas'})")

    user = gh(f"/users/{args.user}", token)
    repos = gh(f"/users/{args.user}/repos?per_page=100&sort=updated", token)
    events = fetch_events(args.user, token)
    print(f"  · {len(repos)} repos, {len(events)} eventos na janela pública")

    out = Path(args.out)
    write(out / "numeros.svg", svg_numbers(user, repos, token, args.with_private_metrics))
    write(out / "atividade.svg", svg_activity(args.user, events))
    print("pronto.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as exc:
        print(f"erro da API do GitHub: {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"erro: {exc}", file=sys.stderr)
        sys.exit(1)
