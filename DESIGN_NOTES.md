# Frontend redesign — source material & plan

Reference material dropped in the repo root:

- `Project Tracking Dashboard - Figma Make.html` — Figma Make **editor page** (the
  "saved from figma.com/make" shell, 980 KB of minified editor JS). Not useful
  as a design source.
- `Project Tracking Dashboard - Figma Make_files/saved_resource.html` — **the
  actual rendered app.** The React DOM is server-captured inline inside
  `<div id="root">`, and the app's compiled CSS (Tailwind v4 output + the
  author's custom rules) is inlined in a `<style data-vite-dev-id=
  "/workspaces/default/code/src/index.css">` block. This is the design source.
- `..._files/client` — the Vite dev bundle (minified, no `sourcesContent`), so
  component source is not recoverable. The DOM + CSS capture is.

## Design language extracted from the capture

| Token | Value |
| --- | --- |
| Page background | `#f7f8fc` |
| Text | `#171a2b` |
| Muted text | `#818698` / `#9296a6` / `#a0a5b7` |
| Border | `#e7e9f0` / `#e8eaf1` / `#e4e6ed` |
| Primary (indigo) | `#635bff`, hover `#554de8`, tint `#f0efff` |
| Success | `#22a06b` (icon green `#18855d` on `#e8f7f1`) |
| Warning | `#f5a524` / text `#cf7700` on `#fff2df` |
| Danger | `#ef5b5b` |
| Info | `#2676d9` on `#eaf3ff` |
| Font | DM Sans (Google Fonts), 400/500/600/700 |
| Sidebar | `248px` fixed, white, `px-4 py-7`, rounded-xl nav items |
| Header | `76px` sticky, `bg-white/90 backdrop-blur-md` |
| Stat cards | `rounded-2xl`, `shadow 0 2px 8px rgba(24,27,45,.025)`, hover `translateY(-2px)` |
| Icon boxes | `36px`, `rounded-[10px]`, four colour variants |
| Progress bars | `h-1.5 rounded-full bg-[#eeeff4]`, per-project accent colour |
| LeetCode ring | `conic-gradient(#22a06b 0 194deg, #f5a524 194deg 328deg, #ef5b5b 328deg 360deg)` |
| Charts | rounded pills, accent for the active point, `#d9d8ff` for the rest |
| Avatar chip | initials on `#ddf3eb`, text `#187a56` |

## Mapping design → DevTrack

The design's four nav items are `Overview / Projects / LeetCode / Analytics`.
DevTrack's backend has five real resources, so the nav is **backend-driven**
(decision: user, this branch): Overview, Projects, LeetCode (= DSA Problems),
Tasks, Goals, Analytics.

| Design element | DevTrack source |
| --- | --- |
| "Total projects" stat | `projects.total` |
| "Problems solved" stat | `dsa.total`, hint `dsa.active_days` |
| "Current streak" stat | derived from `dsa.solved_trend` (consecutive days ending today/yesterday) |
| "Completion rate" stat | `goals.completion_rate` |
| Recent projects list | `projects.items` + per-project milestone completion, matching the design's per-row progress bars |
| LeetCode progress ring | `dsa.by_difficulty` (no hardcoded totals) |
| "This week" pill chart | last 7 points of `dsa.solved_trend` |
| Sidebar momentum card | derived (streak vs. personal best) |
| Header identity chip | `/auth/me` (`full_name`, `email`) |

`GET /analytics/dashboard` is extended with `projects.items[].milestone_total`,
`milestone_completed` and `progress_percent` so the Overview's project list is
real data rather than placeholders (one extra SQL statement; the Branch F
perf suite pins the count).

## Out of scope (intentionally not built)

- Global search input and notifications button from the design's header: they
  have no backend behind them, so shipping them would mean shipping dead UI.
- A `/settings` page (the design links "Settings"): no settings API exists.
- Dark mode: the design is light-only.
