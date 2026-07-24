# Changelog

## [0.4.2](https://github.com/firo1919/telefeed/compare/v0.4.1...v0.4.2) (2026-07-24)


### Bug Fixes

* Update pyproject.toml to include openai and anthropic as required ([b46812a](https://github.com/firo1919/telefeed/commit/b46812ac18b74943454a47e7a35c66de9fa41e0e))
* Update pyproject.toml to include openai and anthropic as required ([20808e0](https://github.com/firo1919/telefeed/commit/20808e0077f1d51e8a4964975f97a61879a9625c))

## [0.4.1](https://github.com/firo1919/telefeed/compare/v0.4.0...v0.4.1) (2026-07-24)


### Bug Fixes

* service.py to fix wrong service file location ([5fb4811](https://github.com/firo1919/telefeed/commit/5fb481124fe153d79a50a42be3e39f1b072145e6))
* service.py to fix wrong service file location ([840905c](https://github.com/firo1919/telefeed/commit/840905c8b2320a9b27f0fd579a8dd918e650cfde))

## [0.4.0](https://github.com/firo1919/telefeed/compare/v0.3.0...v0.4.0) (2026-07-24)


### Features

* added BM25 relevance scoring for area descriptions ([410a560](https://github.com/firo1919/telefeed/commit/410a560b801f8ceae4da2327c6085c8ceda3d57c))
* pagination for match feed with prev/next buttons ([4e2d6d3](https://github.com/firo1919/telefeed/commit/4e2d6d3184ac0cef6cb81e48f30e6062fbe86f43))


### Bug Fixes

* removed unread requirement backfill logic to fetch all messages for channels ([2a4c117](https://github.com/firo1919/telefeed/commit/2a4c1177bbf0f4b7e2c5ff21789d964256f219dc))

## [0.3.0](https://github.com/firo1919/telefeed/compare/v0.2.0...v0.3.0) (2026-07-22)


### Features

* Add FastAPI backend for TeleFeed Web UI with config, auth, and live feed support ([93fbaf0](https://github.com/firo1919/telefeed/commit/93fbaf0f89bf650e23625dd0eac8097a80006eac))
* added build and publish steps for web UI and Python package ([6234c1c](https://github.com/firo1919/telefeed/commit/6234c1c5e1c90ed632ddddf2b33459052519d28a))
* web interface with FastAPI backend and Vite frontend ([fae7f5c](https://github.com/firo1919/telefeed/commit/fae7f5c1ea751f4cfd712c7e3c1bffdb467e421e))

## [0.2.0](https://github.com/firo1919/telefeed/compare/v0.1.0...v0.2.0) (2026-07-21)


### Features

* add multi-provider AI scoring support (Gemini, OpenAI, Anthropic, Ollama, OpenRouter) ([cbfa446](https://github.com/firo1919/telefeed/commit/cbfa4462e9448079128310da100a3ea8c5baf60f))
* added TeleFeedEngine class to centralize feed processing ([97c46ec](https://github.com/firo1919/telefeed/commit/97c46ec51f3b4b914115541b3eb576260da3bc31))
* Append URL to desktop notification body for visibility ([c2cea52](https://github.com/firo1919/telefeed/commit/c2cea52df92647d7fb9c554e25fd6652518b7c24))
* cache channel list to improve performance ([28aa020](https://github.com/firo1919/telefeed/commit/28aa0200bef7a21345000de22678ecd174acf8e6))
* update TeleFeed service management for Windows and Linux ([e0ea323](https://github.com/firo1919/telefeed/commit/e0ea323aa7eb1f36f8ff417e132c2a79ff457edf))


### Bug Fixes

* ci workflow to include all-ai dependencies ([7a170c8](https://github.com/firo1919/telefeed/commit/7a170c87fb1234b0257107eea9a067f755cc5363))
* test seen messages with new check_and_mark_seen function ([f9845fb](https://github.com/firo1919/telefeed/commit/f9845fbf96942aa9470b1d4011732f463bfc3764))

## 0.1.0 (2026-07-20)


### Features

* Add GitHub Actions workflows for CI and release automation ([dab49ef](https://github.com/firo1919/telefeed/commit/dab49efbdcedbf1e3bdbe11a763e2bf6c0c0030d))
* background service ([fdbf7c0](https://github.com/firo1919/telefeed/commit/fdbf7c0692b3e45c12620ef2673c6b709a280650))
* **cli:** add init, doctor, service commands, and --notify flag ([b821854](https://github.com/firo1919/telefeed/commit/b82185491e6e376c84d6cb38a411c1b2ab66f5d8))
* **config:** consolidate credentials into config.yaml and add XDG path resolution ([a51470f](https://github.com/firo1919/telefeed/commit/a51470f65ca2f37d7a98676b15243f7520a17718))
* **notifications:** add desktop OS popups and Telegram Bot push alerts ([d7d5846](https://github.com/firo1919/telefeed/commit/d7d58460c09790e52f6cced1e829ba8755d81a82))
* **service:** add systemd user service installer and CLI management subcommands ([8f760c5](https://github.com/firo1919/telefeed/commit/8f760c5f032baed8dfaba294e42772596f8613a1))


### Documentation

* **packaging:** update pyproject.toml dependencies and README setup guide ([eeafc50](https://github.com/firo1919/telefeed/commit/eeafc504b204e410bdde05fbb2fd120bf6b0a930))
