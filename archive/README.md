# archive/

Data we keep but do not publish (GitHub Pages publishes only `data/`).

- `chessbase_calendar.json`: the last snapshot of the ChessBase India calendar source (30 events,
  as of 28 Nov 2026). The source is switched off with `"publish": false` in
  `config/sources.json`, because ChessBase India's Terms of Use ask not to scrape the site in bulk
  without written permission (see `docs/PERMISSION_EMAILS.md`). The code is still there.

  To switch it back on once they agree: move this file back to `data/sources/`, set
  `"chessbase_calendar": {"enabled": true}` in `config/sources.json`, and run the build.
