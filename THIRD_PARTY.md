# Third-party notes

- Runtime dependency: [websocket-client](https://github.com/websocket-client/websocket-client),
  distributed under its upstream Apache-2.0 license.
- Development tools: [pytest](https://github.com/pytest-dev/pytest) and
  [Ruff](https://github.com/astral-sh/ruff); they are not runtime dependencies.
- Samsung's local Art protocol was studied using
  [samsung-tv-ws-api](https://github.com/NickWaterton/samsung-tv-ws-api), commit
  `fe95ef1d784cd32f49bf9a07ec479576574eea07`. That project is LGPL-3.0.
  This repository contains an original, limited client, not vendored upstream
  source. The `off` timer value already appeared in upstream implementations;
  the hardware finding here is acceptance by the tested S95H.
- Additional protocol references included
  [ha-samsungtv-smart](https://github.com/TheFab21/ha-samsungtv-smart), commit
  `8c7000522b4045b42ff26d129d8d5fe9daf280cb`, and Samsung's consumer TV IP command
  documentation. Their source and downloads are not included in this repository.
- Samsung documentation and manuals are linked rather than redistributed.
  No Samsung artwork or subscription content is supplied.
- A project reuse license has not been selected. Dependency licenses remain
  applicable to the dependencies.
