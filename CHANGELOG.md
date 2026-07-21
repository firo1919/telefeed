# Changelog

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
