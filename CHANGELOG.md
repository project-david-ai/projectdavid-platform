## [1.30.1](https://github.com/project-david-ai/projectdavid-platform/compare/v1.30.0...v1.30.1) (2026-04-04)


### Bug Fixes

* **deps:** trigger release for pinned image digests ([e98def3](https://github.com/project-david-ai/projectdavid-platform/commit/e98def35ee1696078c2fa26a5774350b7f4bdaee))

# [1.30.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.29.0...v1.30.0) (2026-04-03)


### Bug Fixes

* remove unused result variable in WorkerNodeOrchestrator.join ([5acc1d4](https://github.com/project-david-ai/projectdavid-platform/commit/5acc1d44b58fe49f048c0f5df0213bab3452ed1d))


### Features

* migrate to Ray Serve architecture with profile-based training stack ([25b9c1b](https://github.com/project-david-ai/projectdavid-platform/commit/25b9c1be949616dbc0e969749a67b0680fde02a0))
* migrate to Ray Serve architecture with profile-based training stack ([497ac8d](https://github.com/project-david-ai/projectdavid-platform/commit/497ac8da2f3855277ecd75322c17147c5ac467a8))
* migrate to Ray Serve architecture with profile-based training stack ([e4b3983](https://github.com/project-david-ai/projectdavid-platform/commit/e4b39833d6f0525ce214a81861456f55ce5e8d54))

# [1.29.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.28.0...v1.29.0) (2026-03-30)


### Features

* interactive Ray cluster join walkthrough on first --training invocation ([9322db3](https://github.com/project-david-ai/projectdavid-platform/commit/9322db3fabb2a5f3fa1fb41091b37ff99c59f393))


### Reverts

* remove vllm from --training flag, DeploymentSupervisor manages vllm lifecycle ([55c7a49](https://github.com/project-david-ai/projectdavid-platform/commit/55c7a498db0d747576e00c66b1efe7fabb1609b5))

# [1.28.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.27.0...v1.28.0) (2026-03-30)


### Features

* --training flag starts vllm without ollama via _extra_services ([31d7b02](https://github.com/project-david-ai/projectdavid-platform/commit/31d7b02dcdb5e20e0493d5185993639701e030f6))

# [1.26.0-dev.2](https://github.com/project-david-ai/projectdavid-platform/compare/v1.26.0-dev.1...v1.26.0-dev.2) (2026-03-27)


### Features

* sovereign cluster docker + Gold Standard CI ([47f63d6](https://github.com/project-david-ai/projectdavid-platform/commit/47f63d68dc27130f1231c20b7bf3b7cabaf340fa))

# [1.26.0-dev.1](https://github.com/project-david-ai/projectdavid-platform/compare/v1.25.1...v1.26.0-dev.1) (2026-03-26)


### Bug Fixes

* add type annotation for injected list to satisfy mypy strict ([9ca2f91](https://github.com/project-david-ai/projectdavid-platform/commit/9ca2f91ba5980b8b5be5fc57781bd75809fd1def))
* **ci:** update security scanner paths to projectdavid_platform ([ac6e110](https://github.com/project-david-ai/projectdavid-platform/commit/ac6e11031506f971d9017e15b9ecf3d804785568))
* correct training-worker entrypoint and profile default ([5b02cd8](https://github.com/project-david-ai/projectdavid-platform/commit/5b02cd846f76e9a724875ef79167dd3149c88e44))
* correct training-worker entrypoint and profile default ([138f2fd](https://github.com/project-david-ai/projectdavid-platform/commit/138f2fdab49381fdff389f8e09b0b461676c44ea))
* correct training-worker entrypoint and profile default ([c17d3d0](https://github.com/project-david-ai/projectdavid-platform/commit/c17d3d0ce3f11fc30e550ed234c7f23767b068e3))
* nosec B105 for intentional empty HF_TOKEN default ([d0e89e3](https://github.com/project-david-ai/projectdavid-platform/commit/d0e89e3fac491c4b17c0b85cb00d3aab4214a9ba))
* sync start_orchestration source with _ensure_dockerignore and configure output ([3bfe152](https://github.com/project-david-ai/projectdavid-platform/commit/3bfe152313293f09e15e3fb03be4db47b9c4b6c5))


### Features

* sovereign cluster docker + CI gold standard fixes ([55bf0c4](https://github.com/project-david-ai/projectdavid-platform/commit/55bf0c43e1a190029854f19100de4414969ba4f4))

## [1.25.1](https://github.com/project-david-ai/projectdavid-platform/compare/v1.25.0...v1.25.1) (2026-03-24)


### Bug Fixes

* correct training-worker entrypoint and profile default ([e8cba62](https://github.com/project-david-ai/projectdavid-platform/commit/e8cba62eb28f079420a7b76a011dd3434136be91))

# [1.25.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.24.5...v1.25.0) (2026-03-24)


### Features

* defer ADMIN_API_KEY generation to bootstrap-admin command ([14717ea](https://github.com/project-david-ai/projectdavid-platform/commit/14717ea393107299c26f2948f8937d6325b2f5c7))

## [1.24.5](https://github.com/project-david-ai/projectdavid-platform/compare/v1.24.4...v1.24.5) (2026-03-24)


### Bug Fixes

* prevent automatic generation of admin credentials during initial setup ([e21dc77](https://github.com/project-david-ai/projectdavid-platform/commit/e21dc771b6765c0f5fd6c714787247208a8a985b))

## [1.24.4](https://github.com/project-david-ai/projectdavid-platform/compare/v1.24.3...v1.24.4) (2026-03-24)


### Bug Fixes

* prevent automatic generation of admin credentials during initial setup ([86d5000](https://github.com/project-david-ai/projectdavid-platform/commit/86d500037674cf73b905a0d01d7ede394e6a5dd0))
* prevent automatic generation of admin credentials during initial setup ([8ac577d](https://github.com/project-david-ai/projectdavid-platform/commit/8ac577dea91359ffd1a7780ef100c42f985b819d))

## [1.24.3](https://github.com/project-david-ai/projectdavid-platform/compare/v1.24.2...v1.24.3) (2026-03-24)


### Bug Fixes

* prevent automatic generation of admin credentials during initial setup ([86876c6](https://github.com/project-david-ai/projectdavid-platform/commit/86876c654998e87b03517d95ff2b78cdc6e193aa))
* prevent automatic generation of admin credentials during initial setup ([77bacf8](https://github.com/project-david-ai/projectdavid-platform/commit/77bacf8b3e1a6fa8e39333d529213d6efb71e87a))

## [1.24.2](https://github.com/project-david-ai/projectdavid-platform/compare/v1.24.1...v1.24.2) (2026-03-24)


### Bug Fixes

* prevent automatic generation of admin credentials during initial setup ([cd9886c](https://github.com/project-david-ai/projectdavid-platform/commit/cd9886c2561bc8e725970a2bbaf3a84fab24eb1d))
* prevent automatic generation of admin credentials during initial setup ([8eb31d8](https://github.com/project-david-ai/projectdavid-platform/commit/8eb31d82e8fe94c6937fdc0221d3abc5267974e9))
* prevent automatic generation of admin credentials during initial setup ([8a91a47](https://github.com/project-david-ai/projectdavid-platform/commit/8a91a4747abe4f5f3c3064103380febff15d2634))

## [1.24.1](https://github.com/project-david-ai/projectdavid-platform/compare/v1.24.0...v1.24.1) (2026-03-24)


### Bug Fixes

* resolve ruff linting issues (E722, F841, F401) ([9ca44bc](https://github.com/project-david-ai/projectdavid-platform/commit/9ca44bcc2c037c6e56a2693b270fa06dbb9628f9))

# [1.24.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.23.1...v1.24.0) (2026-03-24)


### Bug Fixes

* resolve ruff linting issues (E722, F841, F401) ([f624543](https://github.com/project-david-ai/projectdavid-platform/commit/f624543013f103beb43a15047ea1b33f9872966e))
* resolve ruff linting issues (E722, F841, F401) ([9216f64](https://github.com/project-david-ai/projectdavid-platform/commit/9216f642da0c7961caaf56ede8db8194250a8b9d))
* resolve ruff linting issues (E722, F841, F401) ([4a35886](https://github.com/project-david-ai/projectdavid-platform/commit/4a35886d1848b5bd36cdd0d37ba4faa7c8edfa31))
* resolve ruff linting issues (E722, F841, F401) ([b6804eb](https://github.com/project-david-ai/projectdavid-platform/commit/b6804ebf478fe14651ed0b5954a5f419ee052e0c))
* resolve ruff linting issues (E722, F841, F401) ([0134179](https://github.com/project-david-ai/projectdavid-platform/commit/01341798c3a1fd203a56b1d53f9129069ec067c3))
* resolve ruff linting issues (E722, F841, F401) ([2879df6](https://github.com/project-david-ai/projectdavid-platform/commit/2879df6233a8883f2f4394d3ef898333ac6ea266))


### Features

* integrate sovereign forge training stack and silence secret output ([767998b](https://github.com/project-david-ai/projectdavid-platform/commit/767998bc1ba837dcf82cb43fbd6716fe1e9ac14a))
* integrate sovereign forge training stack and silence secret output ([b1da01f](https://github.com/project-david-ai/projectdavid-platform/commit/b1da01f3033b74ff620b02638c4be711a69d933a))

## [1.23.1](https://github.com/project-david-ai/projectdavid-platform/compare/v1.23.0...v1.23.1) (2026-03-24)


### Bug Fixes

* remove AUTO_MIGRATE flag from distribution compose ([a6dc3f9](https://github.com/project-david-ai/projectdavid-platform/commit/a6dc3f94043a3bde94fc966b131191db55f4c240))

# [1.23.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.22.0...v1.23.0) (2026-03-24)


### Features

* add docker-compose.training.yml overlay for Sovereign Forge ([cb59b8d](https://github.com/project-david-ai/projectdavid-platform/commit/cb59b8d8b71ab9c3f8c15b08af95e0843c836af7))
* add port conflict detection for --training overlay ([bb58a85](https://github.com/project-david-ai/projectdavid-platform/commit/bb58a859d9af23c144034571e48abac30946e891))
* complete Sovereign Forge integration — four-step rollout ([57fd90a](https://github.com/project-david-ai/projectdavid-platform/commit/57fd90a6c9daf3f53ecbb36e6d4753df82930001))
* complete Sovereign Forge integration — four-step rollout ([28baa6d](https://github.com/project-david-ai/projectdavid-platform/commit/28baa6d04b3d98367fd3d47b7a3882f4fb3b6eb3))
* complete Sovereign Forge integration — four-step rollout ([1b4e0d1](https://github.com/project-david-ai/projectdavid-platform/commit/1b4e0d11f1c57c5c6cd55db9da53d529c0d2b83a))
* integrate Sovereign Forge training stack as opt-in overlay ([bb860a9](https://github.com/project-david-ai/projectdavid-platform/commit/bb860a98f13f6687489c14c1b5d478210d8940c0))

# [1.22.0](https://github.com/project-david-ai/projectdavid-platform/compare/v1.21.0...v1.22.0) (2026-03-16)


### Features

* add inference provider base URLs for hosted model routing ([00b58af](https://github.com/project-david-ai/projectdavid-platform/commit/00b58afe63720262c3da432ccab88bb45c245170))

# [1.21.0](https://github.com/project-david-ai/platform-docker/compare/v1.20.0...v1.21.0) (2026-03-15)


### Features

* add changelog link to upgrade notice and clarify version usage in orchestration ([879ba4f](https://github.com/project-david-ai/platform-docker/commit/879ba4fe7631cd59744f8bc8066af966f8ef8e5f))

# [1.20.0](https://github.com/project-david-ai/platform-docker/compare/v1.19.0...v1.20.0) (2026-03-15)


### Features

* switch to latest image tags for API and sandbox in Docker Compose configuration ([7c059b3](https://github.com/project-david-ai/platform-docker/commit/7c059b389f84b53fa12b87c5237b63a7cc1f45c3))

# [1.19.0](https://github.com/project-david-ai/platform-docker/compare/v1.18.0...v1.19.0) (2026-03-15)


### Bug Fixes

* correct filename for `ollama` Docker Compose overlay and adjust echo formatting ([6c6c426](https://github.com/project-david-ai/platform-docker/commit/6c6c4261f4d15ba96b711d5ba0ee1507ca5d661d))


### Features

* add independent ollama and vLLM overlays with GPU orchestration updates ([e486b28](https://github.com/project-david-ai/platform-docker/commit/e486b2821d01cce1592fec24724a21cf14c39133))
* add independent ollama and vLLM overlays with GPU orchestration updates ([4be0b86](https://github.com/project-david-ai/platform-docker/commit/4be0b8692a5987ff074b1332ca912f640f42e300))
* add version upgrade detection and `--pull` support to orchestration ([43727c6](https://github.com/project-david-ai/platform-docker/commit/43727c62f25bcb564918f8d9e709555b8c0019ed))
* add version upgrade detection and `--pull` support to orchestration ([f7cf25a](https://github.com/project-david-ai/platform-docker/commit/f7cf25aef194b93807729e2a9474d1d5924988be))

# [1.18.0](https://github.com/project-david-ai/platform-docker/compare/v1.17.0...v1.18.0) (2026-03-15)


### Features

* add version upgrade detection and `--pull` support to orchestration ([527f862](https://github.com/project-david-ai/platform-docker/commit/527f86252ed45298243c3c60ae15c193d429ed58))
* remove stack diagram from README and fix minor echo formatting ([3d45857](https://github.com/project-david-ai/platform-docker/commit/3d4585730d9ef41115655bc4513882d30b0e29a2))

# [1.17.0](https://github.com/project-david-ai/platform-docker/compare/v1.16.0...v1.17.0) (2026-03-15)


### Bug Fixes

* restore correct gpu overlay — wrong file was committed ([1d53c4f](https://github.com/project-david-ai/platform-docker/commit/1d53c4f963106b824c48fdea24508c17351bed0c))
* streamline and enhance docker-compose configuration ([b68dff1](https://github.com/project-david-ai/platform-docker/commit/b68dff1588e77abe511c2af8a6de6bc82dd92de6))


### Features

* enhance Docker stack with expanded services and GPU improvements ([e046e46](https://github.com/project-david-ai/platform-docker/commit/e046e4682da7828160a9012dda5ac3064588e675))
* simplify GPU orchestration by integrating ollama and vLLM services ([7016807](https://github.com/project-david-ai/platform-docker/commit/70168072c9f4468aedb42507b67b0362a88d178d))

# [1.16.0](https://github.com/project-david-ai/platform-docker/compare/v1.15.0...v1.16.0) (2026-03-15)


### Features

* enhance Docker orchestration with new services and improved configs ([b49685b](https://github.com/project-david-ai/platform-docker/commit/b49685bafea8ac6fd850ee22ee23260e19ce7d7f))

# [1.15.0](https://github.com/project-david-ai/platform-docker/compare/v1.14.1...v1.15.0) (2026-03-15)


### Features

* enhance Docker orchestration with new services and improved configs ([f20dd84](https://github.com/project-david-ai/platform-docker/commit/f20dd848d7e14c5ee55228f652ac5fd53d39ea0d))

## [1.14.1](https://github.com/project-david-ai/platform-docker/compare/v1.14.0...v1.14.1) (2026-03-15)


### Bug Fixes

* remove user-related script commands and simplify admin bootstrap ([11114ad](https://github.com/project-david-ai/platform-docker/commit/11114ad681cabbb136be28bed268ea46b6fe11de))

# [1.14.0](https://github.com/project-david-ai/platform-docker/compare/v1.13.0...v1.14.0) (2026-03-15)


### Features

* update stack to use `pdavid` commands and adjust GPU orchestration ([9517a77](https://github.com/project-david-ai/platform-docker/commit/9517a77f231253a9aa060e298da72e143395974c))

# [1.13.0](https://github.com/project-david-ai/platform-docker/compare/v1.12.1...v1.13.0) (2026-03-15)


### Features

* refine README and orchestration setup for clarity and reliability ([71863ea](https://github.com/project-david-ai/platform-docker/commit/71863ea7e9412f3f6a7b8be8ccafbbb37630b7e7))

## [1.12.1](https://github.com/project-david-ai/platform-docker/compare/v1.12.0...v1.12.1) (2026-03-15)


### Bug Fixes

* clean up comments and formatting in `docker-compose.yml` ([5816b0b](https://github.com/project-david-ai/platform-docker/commit/5816b0bef6d1698731fc717e8b09943ae4126a21))

# [1.12.0](https://github.com/project-david-ai/platform-docker/compare/v1.11.0...v1.12.0) (2026-03-14)


### Features

* expand README with API architecture, usage, and SDK documentation ([27260e4](https://github.com/project-david-ai/platform-docker/commit/27260e4de97275a7db378b5d59b962a9f3289e10))

# [1.11.0](https://github.com/project-david-ai/platform-docker/compare/v1.10.0...v1.11.0) (2026-03-14)


### Features

* expand README with API architecture, usage, and SDK documentation ([14b18bb](https://github.com/project-david-ai/platform-docker/commit/14b18bbe0fde45823986446cf9a4ffe255935436))
* expand README with API architecture, usage, and SDK documentation ([7b62e8a](https://github.com/project-david-ai/platform-docker/commit/7b62e8a56e9ec111fd580c7c14fac861fcb7d575))

# [1.10.0](https://github.com/project-david-ai/platform-docker/compare/v1.9.1...v1.10.0) (2026-03-14)


### Features

* expand README with API architecture, usage, and SDK documentation ([a78046c](https://github.com/project-david-ai/platform-docker/commit/a78046cd290e16a4b415ef3dcfc83c3021a10b96))

## [1.9.1](https://github.com/project-david-ai/platform-docker/compare/v1.9.0...v1.9.1) (2026-03-14)


### Bug Fixes

* replace platform commands with pdavid and update documentation ([fbf6448](https://github.com/project-david-ai/platform-docker/commit/fbf6448fb7e3a6a92ab53b606161b2b61d5a580c))

# [1.9.0](https://github.com/project-david-ai/platform-docker/compare/v1.8.4...v1.9.0) (2026-03-14)


### Bug Fixes

* remove unnecessary blank line in test_env_generation tests ([031a5d4](https://github.com/project-david-ai/platform-docker/commit/031a5d40c84be622111187f7035cdd3cc7022d93))
* remove unnecessary blank line in test_env_generation tests ([ef7f510](https://github.com/project-david-ai/platform-docker/commit/ef7f51025da7495e75fa559cf7e84a2576b48648))
* remove unused imports across test files ([f6335a1](https://github.com/project-david-ai/platform-docker/commit/f6335a1b37a9b1851e57af73c4086d8fddb93a75))
* remove unused variables in test_env_generation tests ([2cdc69f](https://github.com/project-david-ai/platform-docker/commit/2cdc69fcf2a6bc90ba195fb2d9ef65fd7a8ea7f1))
* remove unused variables in test_env_generation tests ([6e4b096](https://github.com/project-david-ai/platform-docker/commit/6e4b0963d8b72dc1a9eeedcc21ceb3c699e749e2))
* remove unused variables in test_env_generation tests ([c37105a](https://github.com/project-david-ai/platform-docker/commit/c37105ac0eff3c8fb88d8dba5fb377bd33a46a60))


### Features

* add comprehensive test suite and update documentation ([a3b95b9](https://github.com/project-david-ai/platform-docker/commit/a3b95b99b6c80744d1bbb9f4b52d2a6ac60f5733))
* integrate test step into CI workflow ([6fc7e30](https://github.com/project-david-ai/platform-docker/commit/6fc7e306eb77bcd7297df6a07703b29e18095c1f))

## [1.8.4](https://github.com/project-david-ai/platform-docker/compare/v1.8.3...v1.8.4) (2026-03-14)


### Bug Fixes

* correct and standardize .env and related file paths ([9e49242](https://github.com/project-david-ai/platform-docker/commit/9e49242c6230236b4a3579511cc790e58d8d6c10))

## [1.8.3](https://github.com/project-david-ai/platform-docker/compare/v1.8.2...v1.8.3) (2026-03-14)


### Bug Fixes

* correct and standardize .env and related file paths ([abfe24c](https://github.com/project-david-ai/platform-docker/commit/abfe24c11899d6ba8d9e81011a47d46d0875f865))

## [1.8.2](https://github.com/project-david-ai/platform-docker/compare/v1.8.1...v1.8.2) (2026-03-14)


### Bug Fixes

* update README and compose file paths for consistency ([1f4dc26](https://github.com/project-david-ai/platform-docker/commit/1f4dc26cd10df81237a82bf5b907ffa364912683))

## [1.8.1](https://github.com/project-david-ai/platform-docker/compare/v1.8.0...v1.8.1) (2026-03-14)


### Bug Fixes

* update file paths and adjust packaging for projectdavid-platform ([755b4ba](https://github.com/project-david-ai/platform-docker/commit/755b4ba571970a3d30d5cad31c20b1c73e07c323))

# [1.8.0](https://github.com/project-david-ai/platform-docker/compare/v1.7.0...v1.8.0) (2026-03-14)


### Features

* update CI release workflow to use cycjimmy/semantic-release-action ([e479a01](https://github.com/project-david-ai/platform-docker/commit/e479a01b34719deeddf8b69f78ce5d55cfbd4779))

# [1.7.0](https://github.com/project-david-ai/platform-docker/compare/v1.6.0...v1.7.0) (2026-03-14)


### Features

* initial release of projectdavid-platform with pdavid CLI ([f93df3f](https://github.com/project-david-ai/platform-docker/commit/f93df3f18b6425e0863cf946b9d2086337548cb3))

# [1.6.0](https://github.com/project-david-ai/platform-docker/compare/v1.5.0...v1.6.0) (2026-03-14)


### Features

* update CI workflow to include release and publish steps ([c21e1f7](https://github.com/project-david-ai/platform-docker/commit/c21e1f741b27b47ce5aa90059b79dafb6bf72456))

# [1.5.0](https://github.com/project-david-ai/platform-docker/compare/v1.4.0...v1.5.0) (2026-03-14)


### Features

* replace CLI name from `platform` to `pdavid` and enhance stack management options ([835eb21](https://github.com/project-david-ai/platform-docker/commit/835eb21d077a83348cc6aa6af3326b4fc629d3c0))

# [1.4.0](https://github.com/project-david-ai/platform-docker/compare/v1.3.0...v1.4.0) (2026-03-14)


### Bug Fixes

* correct version script name in releaserc ([48e06c3](https://github.com/project-david-ai/platform-docker/commit/48e06c33ab1191490e738cf8e1c3677694d62365))


### Features

* add .env.example with guided setup instructions and placeholders for config values ([a69fed3](https://github.com/project-david-ai/platform-docker/commit/a69fed3b297ef0fce2e8d4a1e87c1ba7cea291a3))
* add `--no-interpolate` to docker compose validation steps in CI workflow ([2427a92](https://github.com/project-david-ai/platform-docker/commit/2427a92ad7c2f3dae89b04cf6845201b0f87e297))
* add fallback for HF_CACHE_PATH and VLLM_MODEL in docker-compose.gpu.yml to improve usability ([cf6df0e](https://github.com/project-david-ai/platform-docker/commit/cf6df0e59924e565f93a09f54a0be587056da051))
* add fallback for SHARED_PATH in docker-compose volumes to improve usability ([b2889b8](https://github.com/project-david-ai/platform-docker/commit/b2889b89987ada2af29729069427ede230ed1164))
* add package initialization, resolve compose file paths via importlib, and improve CLI documentation for projectdavid-platform ([5091bd4](https://github.com/project-david-ai/platform-docker/commit/5091bd4437167f3f867067903c3dc136cffe03c3))
* remove bootstrap scripts ([bbf1b57](https://github.com/project-david-ai/platform-docker/commit/bbf1b5742be06771d85d96697ef2f0a1d9e20df8))
* remove bootstrap scripts ([bb0dc54](https://github.com/project-david-ai/platform-docker/commit/bb0dc54bbe97ffe32b73c085cef7a189d206f211))
* rename package and update README, CLI commands, and example scripts to reflect "projectdavid-platform" ([e0c2cd9](https://github.com/project-david-ai/platform-docker/commit/e0c2cd9b2a1d93e893f012216aabb51b98843237))
* rename package to projectdavid-platform, bundle compose files for pip distribution ([542dbb5](https://github.com/project-david-ai/platform-docker/commit/542dbb5f2da3e72dd21e365d19c3e433028b9e7b))
* update module reference in modules.xml and cleanup version_control.py ([15e6801](https://github.com/project-david-ai/platform-docker/commit/15e68019d18dc57c9b9119ce7ec7fbc687a1affc))
* update module reference in modules.xml and cleanup version_control.py ([2b5b5f6](https://github.com/project-david-ai/platform-docker/commit/2b5b5f6da32fbe29f72e5e332e2e6d075cdba62b))
* update module reference in modules.xml and cleanup version_control.py ([794acd7](https://github.com/project-david-ai/platform-docker/commit/794acd7f390df40b4d09a865a2a11632c54df885))
* wrap environment variables in docker-compose.yml with quotes ([fad9283](https://github.com/project-david-ai/platform-docker/commit/fad9283eaafad95a9cc33785a674d26932580e72))

# [1.3.0](https://github.com/frankie336/entities/compare/v1.2.0...v1.3.0) (2025-04-19)


### Features

* Add Redis Server to yml ([828458a](https://github.com/frankie336/entities/commit/828458a7c514a77b1003109915094444dc18f119))
* Add Redis Server to yml ([3cae319](https://github.com/frankie336/entities/commit/3cae319ee2c8108b78180ee5be10d8b647da1713))
* Add Redis Server to yml2 ([a79138c](https://github.com/frankie336/entities/commit/a79138c3d906322cd952d1f56bcd76d8a63f9f0f))

# [1.2.0](https://github.com/frankie336/entities/compare/v1.1.0...v1.2.0) (2025-04-19)


### Features

* Add Redis Server to yml ([1aa1c3b](https://github.com/frankie336/entities/commit/1aa1c3b2f426d86165afd81e68c7faad1a7dcadf))

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# [1.1.0](https://github.com/frankie336/entities/compare/v1.0.0...v1.1.0) (2025-04-16)

# Changelog - Notable Changes in Dev Version

## Refactoring and Code Quality Improvements

- **F-String Cleanup:**
  Replaced all f‑strings without any placeholders (F541) with regular string concatenation or proper formatting. This eliminates the flake8 F541 errors.

- **Line Formatting:**
  Split multiple statements on one line (E701 errors) into individual lines for clarity and compliance with PEP 8.

- **Unused Imports Removed:**
  Removed or commented out unused imports (e.g., `getpass`, `dotenv.load_dotenv`, and unused members from `os.path`) to resolve F401 errors.

- **Improved Error Messaging:**
  Enhanced error messages in database connection logic and file I/O operations (such as during credential file writing and .env updates) to be more informative and provide actionable troubleshooting tips.

- **Logging Standardization:**
  Streamlined logging messages across bootstrap and user-creation scripts to ensure consistency and easier debugging during the bootstrap process.

- **Code Comment Cleanup:**
  Removed excessive inline comments and redundant annotations to improve overall readability and maintainability of the scripts.

- **Semantic-Release Alignment:**
  Adjusted version-update commands and file paths (ensuring they correctly reference existing files) to resolve issues with our semantic-release pipeline.

These changes not only resolve the current linting and formatting issues but also enhance the robustness and clarity of our bootstrap and orchestration scripts, ultimately leading to a smoother developer experience.

### Bug Fixes

*.releaserc.json ([c2910f6](https://github.com/frankie336/entities/commit/c2910f6c8cd99393815b15ba7cb2804ac9889f52))
* .releaserc.json[#1](https://github.com/frankie336/entities/issues/1) ([cec1a03](https://github.com/frankie336/entities/commit/cec1a034d62ae71fd6286ec36479143475d0024b))
* syntax issues. ([f21b3a3](https://github.com/frankie336/entities/commit/f21b3a375df72c1af27a3446251de3990bd5d4c7))
* syntax issues[#1](https://github.com/frankie336/entities/issues/1). ([0fa19f0](https://github.com/frankie336/entities/commit/0fa19f05d87d9f7287df485fcb303f83808064e9))


### Features

* unique secrets generate_docker_compose.py ([6ec3efe](https://github.com/frankie336/entities/commit/6ec3efe0599326c2a851d22a020dfe788a963b56))

# 1.0.0 (2025-04-15)


### Bug Fixes

* lint fixes. ([67305f5](https://github.com/frankie336/entities/commit/67305f5b9fd01fece73f40145d90a163c1a95a71))
