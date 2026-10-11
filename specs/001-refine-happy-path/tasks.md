# Tasks: Refine Happy Path

**Input**: Design documents from `specs/001-refine-happy-path/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md

**Tests**: OBRIGATÓRIOS nesta feature. A constituição (princípio VI — test-first no núcleo) e o quickstart exigem testes do núcleo com fakes (implementações falsas dos ports que substituem Notion e agente, sem rede). Toda task de teste lista o caminho exato do arquivo e os nomes dos testes (frases de comportamento, em inglês). Escrever os testes ANTES da implementação correspondente e confirmar que falham antes de implementar.

**Organization**: Tasks agrupadas por user story (US1/US2/US3 da spec.md) para permitir implementação e teste independentes de cada story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependências)
- **[Story]**: A qual user story a task pertence (US1, US2, US3)
- **[P]** marcado somente quando os arquivos são distintos e não há dependência de task incompleta

## Path Conventions

Single project: código em `src/notion_copilot/`, prompts em `prompts/`, testes em `tests/{unit,integration}/` na raiz (conforme plan.md, seção Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialização do projeto e estrutura básica.

- [x] T001 Create the uv project per plan.md: `pyproject.toml` (project `notion-copilot`, Python 3.12, deps `typer`, `pydantic`, `pydantic-settings`, `notion-client`, `platformdirs`; dev deps `pytest`, `ruff`, `mypy`; script `notion-copilot = notion_copilot.cli:app`), `.python-version` com `3.12`, and run `uv sync` to generate `uv.lock`
- [x] T002 [P] Configure lint/type gates in `pyproject.toml`: ruff (lint + format) and mypy strict for `src/notion_copilot/domain/` and `src/notion_copilot/application/`; verify `uv run ruff check .` and `uv run mypy src` pass on the skeleton
- [x] T003 [P] Create package skeleton: `src/notion_copilot/__init__.py`, `src/notion_copilot/domain/__init__.py`, `src/notion_copilot/application/__init__.py`, `src/notion_copilot/adapters/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`
- [x] T004 [P] Create `.env.example` listing `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `NOTION_USER_ID` and the model credential (exact name confirmed in T029 per research R5), with comments and NO values; fix `.gitignore` so the pattern `.env.*` no longer ignores `.env.example` (add `!.env.example` exception)
- [x] T005 [P] Create `.mcp.json` at repo root with the Z.ai MCP servers `web_search_prime` and `web_reader` only (ADR-005, research R5)
- [x] T006 [P] Record ADR-007 in `docs/notion-copilot-adrs.md`: scheduler interval 15 → 5 minutes, superseding ADR-001 — including the ADR-001 phrase that allowed selecting cards with IA status "vazio, ❓ ou ⚠️" (FR-004 allows only empty), citing FR-003 (lock) and FR-005 (⏳ never selected) as the safety mechanisms
- [x] T007 [P] Promote ADR-006 from Proposto to Aceito in `docs/notion-copilot-adrs.md`, citing research R1 (markdown endpoints `GET`/`PATCH /v1/pages/{page_id}/markdown`, API `2026-03-11`) as confirmed evidence

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infraestrutura que TODAS as user stories usam: modelos do domínio, ports (Protocols que definem a fronteira entre núcleo e adapters), configuração, log estruturado e lock de rodada.

**⚠️ CRITICAL**: Nenhuma user story pode começar antes desta fase completa.

### Tests for Foundational (write FIRST, confirm they FAIL)

- [x] T008 [P] Write unit tests in `tests/unit/domain/test_models.py`: "accepts the golden example from contracts/agent-output.md"; "rejects a title longer than 80 characters"; "rejects output missing any of the seven section keys"; "rejects executor_suggestion outside HUMANO and IA"; "rejects card result attempts outside 1–3"; "formats run_id as YYYYMMDDTHHMM-xxxx (e.g. 20261010T1425-7f3a)"
- [x] T009 [P] Write unit test in `tests/unit/domain/test_stages.py`: "the refine stage declares prompts/refine.md and only the web tools web_search_prime and web_reader" (constituição III)
- [x] T010 [P] Write unit tests in `tests/unit/test_config.py`: "rejects an .env file with permissions looser than 600"; "resolves the state dir via platformdirs and exposes absolute paths for .mcp.json and prompts/"
- [x] T011 [P] Write unit tests in `tests/unit/adapters/test_logging_fs.py`: "writes one JSON line per event with ts, run_id, card_id (when present), stage, event, duration_s (when present)"; "saves the agent stream-json trail in the state dir under a name derived from run_id"; "never writes configured secrets into events or trails" (RNF-O5)
- [x] T012 [P] Write unit tests in `tests/unit/adapters/test_lock_fs.py`: "reports the lock busy when another round holds it"; "allows acquiring the lock again after release"

### Implementation for Foundational

- [x] T013 Implement `src/notion_copilot/domain/models.py`: enums `Pipeline`, `IAStatus`, `Executor`; `Card` (page_id, title, pipeline, executor, ia_status, ia_updated_at: datetime | None, created_at, body_markdown, has_refinement, has_original_record); `CardResult` (outcome: `success | needs_you | error | skipped_moved | skipped_already_refined`, error_kind: str | None, attempts: int "1–3", duration_s: float); `Run` (run_id, started_at/finished_at, selected, results); `RefineOutput` (title: str não vazia "≤ 80 chars"; sections: as 7 chaves obrigatórias `contexto`, `links_guardados`, `acoes_sugeridas`, `o_que_ja_adiantei`, `perguntas_abertas`, `prompt_sugerido`, `executor_sugerido`; blocking_questions: list[str]; executor_suggestion: `HUMANO | IA`) + gerador de `run_id` no formato `20261010T1425-7f3a` (data-model.md, restrições citadas verbatim)
- [x] T014 Implement `src/notion_copilot/domain/stages.py`: tabela de etapas com uma linha para `refine` (arquivo de prompt, allowlist de ferramentas `web_search_prime` + `web_reader`, descrição) — extensível a Plan/Execute sem tocar o loop (constituição IX; evita Temporal Decomposition)
- [x] T015 Implement `src/notion_copilot/application/ports.py`: Protocols `NotionReader`, `NotionWriter`, `AgentRunner`, `Clock`, `RoundLock` — assinaturas cobrem: consulta de elegíveis (FR-004), varredura de ⏳ abandonados (FR-017), leitura de markdown da página (R9), escrita de seções/título/propriedades (FR-009), transição de IA status (reescreve `IA atualizado em` junto), comentário com menção (FR-014), execução do agente com timeout, agora, acquire/release do lock
- [x] T016 Implement `src/notion_copilot/config.py`: pydantic-settings lendo `.env` (permissão verificada = 600, mensagem dizendo o que falta e como corrigir); state dir via `platformdirs` (lock + logs, research R3); caminhos absolutos para `.mcp.json` e `prompts/`; constantes: `max_cards_per_round = 5`, `agent_timeout_s = 600` (10 min), `stale_after_s = 1800` (30 min), `retry_backoff_s = [30, 120]` (research R8)
- [x] T017 Implement `src/notion_copilot/adapters/logging_fs.py`: eventos JSON no state dir (campos do data-model: ts, run_id, card_id?, stage `preflight|select|refine|write|move|comment`, event, duration_s?, detail?) + rastro `stream-json` por execução do agente; nenhum segredo em nenhuma saída (RNF-O1/O2/O3/O5)
- [x] T018 Implement `src/notion_copilot/adapters/lock_fs.py`: `RoundLock` com `fcntl.flock` no state dir (`round.lock`), acquire no início e release em `try/finally` (research R3)

**Checkpoint**: Fundação pronta (modelos, ports, config, log, lock) — implementação das user stories pode começar.

---

## Phase 3: User Story 1 - Refino automático de ponta a ponta (Priority: P1) 🎯 MVP

**Goal**: Card elegível na raia To Refine é selecionado, marcado ⏳, refinado pelo agente (somente busca web), validado, gravado pelo orquestrador e movido para Refined com IA status vazio.

**Independent Test** (spec.md US-1): mover um card real (ex.: "ligar pra estacio pra saber como pegar bolsa do curso") para To Refine e observar o board: em minutos o card está em Refined com a seção `## 🔍 Refinamento` preenchida.

### Tests for User Story 1 (write FIRST, confirm they FAIL)

- [x] T019 [P] [US1] Write unit tests in `tests/unit/domain/test_rules_selection.py`: "selects only cards in To Refine with empty IA status"; "orders selected cards oldest first and limits to 5" (FR-004); "never selects a card with running, needs-you or error status" (FR-005)
- [x] T020 [P] [US1] Write unit tests in `tests/unit/domain/test_refine_ops.py`: "builds one fill operation per section with the template heading as old_str and heading plus body as new_str"; "keeps the template heading unchanged as the first line of each new_str" (research R1: cada `old_str` casa exatamente uma vez; headings vêm do template, corpos nunca contêm headings)
- [x] T021 [P] [US1] Write unit tests in `tests/unit/application/test_run_round.py` (fakes dos ports): "acquires the lock, runs preflight, selects and processes each card, then releases the lock"; "stops with exit code 2 when the lock is already held, without querying for cards"; "ends an empty-queue round after a single query, writing nothing"; "dry-run lists what it would do without writing anything"; "processes only the given card in --card mode and refuses ineligible cards with card_not_eligible" (contracts/cli-commands.md)
- [x] T022 [P] [US1] Write unit tests in `tests/unit/application/test_process_card.py` (fakes): "marks the card running (IA status ⏳ plus IA atualizado em) before invoking the agent" (FR-005); "delivers title, properties and body inside the prompt built from prompts/refine.md" (FR-007/FR-008); "treats invalid agent JSON as a permanent error with no retry" (research R8); "writes each of the seven sections through the writer, one update per section" (FR-009/FR-010); "rewrites the title and fills the Executor property only when it is empty"; "moves the card to Refined and clears IA status on success without blocking questions" (FR-011)
- [x] T023 [P] [US1] Write integration tests in `tests/integration/test_notion_api.py` against recorded API responses (sem rede): query de elegíveis retornando Cards; `GET .../markdown`; payload de `update_content` (comando do `PATCH /v1/pages/{page_id}/markdown`); atualização de propriedades escrevendo IA status e `IA atualizado em` juntos; mudança de Pipeline para Refined
- [x] T024 [P] [US1] Write integration tests in `tests/integration/test_claude_cli.py` against recorded/faked subprocess output: command line contém somente as ferramentas web em `--allowedTools`, `--mcp-config` com caminho absoluto e `--output-format stream-json` (FR-008, research R5); credencial e `ANTHROPIC_BASE_URL` passadas somente ao subprocesso (RNF-S6); parse do stream extrai o JSON final; timeout de 600s interrompe o processo

### Implementation for User Story 1

- [x] T025 [US1] Create `prompts/refine.md` per `specs/001-refine-happy-path/contracts/agent-output.md`: regras dos 7 corpos de seção, todo fato verificado cita fonte com link / fato sem fonte marcado como Hipótese (FR-010), headings proibidos nos corpos, formato JSON de saída exato do contrato (RNF-M4)
- [x] T026 [P] [US1] Implement `src/notion_copilot/adapters/prompts_fs.py`: carrega `prompts/refine.md` por caminho absoluto da config
- [x] T027 [US1] Implement `src/notion_copilot/domain/rules.py` (parte 1): seleção/elegibilidade (filtro `pipeline == TO_REFINE` **e** `ia_status == vazio`, ordenação por `created_time` asc, limite de 5 — FR-004) e construtor de operações de preenchimento (`old_str` = heading do template, `new_str` = heading + corpo)
- [x] T028 [US1] Implement `src/notion_copilot/adapters/notion_api.py` (parte 1): SDK `notion-client` encapsulado; `users.me` (pré-flight), `databases.retrieve` (propriedades esperadas `Pipeline`, `Executor`, `IA status`, `IA atualizado em` + template com esqueleto 🔍 — R1), `databases.query` (elegíveis), `pages.retrieve`, `GET /v1/pages/{page_id}/markdown`, `update_content` do `PATCH /v1/pages/{page_id}/markdown`, `pages.update` (título/propriedades). Ponto de verificação (research R2): se `notion-client` não expuser o endpoint markdown, chamada REST (`client.request`) somente para este endpoint dentro deste arquivo
- [x] T029 [US1] Implement `src/notion_copilot/adapters/claude_cli.py`: subprocesso `claude -p <prompt> --output-format stream-json --verbose --allowedTools <somente web_search_prime e web_reader> --mcp-config <absoluto> --max-turns <N> --model <modelo>` com env `ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic` e credencial somente ao subprocesso; timeout 600s; rastro salvo via logging (research R5). Verificar na máquina o nome exato da credencial (`ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY`) e o prefixo das ferramentas MCP com `claude mcp list`; fixar em `config.py` e atualizar `.env.example` (T004)
- [x] T030 [US1] Implement `src/notion_copilot/application/process_card.py` (caminho feliz): marca ⏳ → monta prompt (título, propriedades, corpo) → invoca agente → valida JSON com `RefineOutput` (Pydantic na fronteira) → preenche as 7 seções via update_content → reescreve título + Executor (só se vazia) → move para Refined + limpa IA status; um evento JSON por etapa (refine|write|move) (FR-005/007/009/010/011)
- [x] T031 [US1] Implement `src/notion_copilot/application/run_round.py`: lock → pré-flight (FR-002: `.env` 600 e campos, `users.me`, schema+template do banco, executável `claude --version`, capabilities Read content/Update content/Insert comments, `prompts/refine.md` e `.mcp.json` presentes) → seleção → loop de cards → eventos; flags `--card` e `--dry-run` (contracts/cli-commands.md)
- [x] T032 [US1] Implement `src/notion_copilot/cli.py` (typer): comandos `run` e `verify`; `verify` roda o pré-flight isolado e imprime lista ✔/✘ com, para cada falha, o que falta e como corrigir; exit codes `0` concluída / `1` pré-flight / `2` lock ocupado / `3` cards em erro (o `3` passa a disparar de fato na US3)

**Checkpoint**: US-1 funcional e testável de forma independente — card em To Refine chega em Refined refinado. Este é o MVP.

---

## Phase 4: User Story 2 - Registro original preservado (Priority: P2)

**Goal**: Antes de qualquer reescrita de título, o texto exato da captura é copiado para o bloco "📝 Registro original", nunca editado; reprocessamento não duplica 📝 nem seção 🔍 (idempotência).

**Independent Test** (spec.md US-2): criar um card com título confuso, processá-lo e comparar o bloco 📝 com o título original digitado — devem ser idênticos.

### Tests for User Story 2 (write FIRST, confirm they FAIL)

- [x] T033 [P] [US2] Write unit tests in `tests/unit/domain/test_idempotency_markers.py`: "detects the 📝 Registro original block"; "detects a filled section body between a template heading and the next heading"; "does not treat the template 🔍 skeleton alone as a refinement" (research R9 — heading sozinho não é marcador)
- [x] T034 [P] [US2] Write unit tests in `tests/unit/application/test_original_record.py` (fakes): "creates the 📝 block with the exact capture text before any title rewrite and before the 🔍 section" (FR-006, US-2.1); "does not create a second 📝 block when the marker is present" (FR-015); "ends an already-refined card as skipped_already_refined: moved to Refined, empty status, no rewrites" (R9); "fills the sections while preserving an existing 📝 from an interrupted run" (R9)

### Implementation for User Story 2

- [x] T035 [US2] Implement in `src/notion_copilot/domain/rules.py` (parte 2): marcadores puros `has_original_record` e `has_refinement` sobre a string markdown (a página é a verdade — research R9) e o construtor do bloco 📝 via update_content com `old_str` = `## 🔍 Refinamento` e `new_str` = `📝 Registro original` + texto exato da captura + `## 🔍 Refinamento` (posiciona antes da seção — R1)
- [x] T036 [US2] Integrate markers into `src/notion_copilot/application/process_card.py`: ler markdown antes de escrever; 📝 existente → não recria nem altera; seção já preenchida → não reescreve; já refinado → desfecho `skipped_already_refined` (mover para Refined, IA status vazio, nenhuma escrita); 📝 criado antes da reescrita do título (FR-006/FR-015)

**Checkpoint**: US-1 e US-2 funcionam de forma independente — reprocessar um card não cria duplicatas (SC-002).

---

## Phase 5: User Story 3 - Falha visível e rodada que continua (Priority: P3)

**Goal**: Falha, demora ou bloqueio de um card fica visível no board (⚠️ ou ❓) com comentário mencionando a usuária e o `run_id`; os demais cards da rodada continuam.

**Independent Test** (spec.md US-3): simular um card que causa erro no agente e observar: o card fica ⚠️ com comentário, e um segundo card elegível na mesma rodada é processado até o fim.

### Tests for User Story 3 (write FIRST, confirm they FAIL)

- [x] T037 [P] [US3] Write unit tests in `tests/unit/domain/test_stale_and_retry.py`: "marks a running card stale when IA atualizado em is older than 30 minutes" (FR-017); "does not mark a running card stale within 30 minutes"; "classifies network errors and Notion 429/5xx as retryable"; "classifies agent invalid JSON and Notion 4xx as permanent" (research R8); "classifies agent timeout as permanent — no retry" (decisão 2026-10-10, R8)
- [x] T038 [P] [US3] Write unit tests in `tests/unit/application/test_failure_visibility.py` (fakes): "marks only the failing card ⚠️ in To Refine and continues the round with the others" (FR-013); "marks the card ⚠️ after two retries with 30s and 120s backoff" (FR-016); "ends a card with blocking questions in Refined with ❓ and a comment mentioning the user and run_id" (FR-012/FR-014); "leaves a comment mentioning the user and run_id whenever the status becomes ⚠️ or ❓" (FR-014, menção via `NOTION_USER_ID`); "marks a stale running card ⚠️ with a comment before selecting new cards" (FR-017, R7); "writes nothing and logs card_moved_during_processing when the card changed pipeline, restoring empty status" (R10, `skipped_moved`); "ends the round with exit code 3 when at least one card errored"
- [x] T039 [P] [US3] Write integration tests in `tests/integration/test_notion_comments.py` against recorded responses: `POST /v1/comments` com `rich_text` = menção de user (`NOTION_USER_ID`) + texto com `run_id`; resposta 403 sem a capability Insert comments traduzida como erro acionável (research R6)

### Implementation for User Story 3

- [x] T040 [US3] Implement in `src/notion_copilot/domain/rules.py` (parte 3): `is_stale` (compara `IA atualizado em` com o port `Clock`, 30 min — FR-017) e classificação de erros temporário vs. permanente (rede, 429/5xx = temporário; JSON inválido do agente, 4xx, timeout = permanente — research R8)
- [x] T041 [US3] Implement failure paths in `src/notion_copilot/application/process_card.py`: retry manual (laço, até 2 novas tentativas, backoff 30s/120s da config) só para temporários; esgotadas as tentativas ou erro permanente → ⚠️ + comentário; `blocking_questions` não vazio → Refined + ❓ + comentário (decisão é do código — R11); releitura das propriedades antes de gravar e `skipped_moved` se o card mudou de raia (R10); nenhum card termina ⏳ (FR-018)
- [x] T042 [US3] Implement in `src/notion_copilot/application/run_round.py`: varredura de ⏳ abandonados antes da seleção (query `IA status = ⏳` AND `IA atualizado em < agora − 30 min` → cada card ⚠️ + comentário — FR-017, R7) e exit code 3 quando a rodada teve cards em erro (contracts/cli-commands.md)
- [x] T043 [US3] Implement comments in `src/notion_copilot/adapters/notion_api.py`: `comments.create` com menção de user + `run_id` (research R6); verificação das capabilities **Read content**, **Update content** e **Insert comments** no pré-flight/`verify` (sem elas a API retorna 403 — R1/R6)

**Checkpoint**: US-1, US-2 e US-3 funcionam de forma independente — nenhuma falha silenciosa (SC-003).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentação de setup, validação end-to-end e gates de qualidade.

- [ ] T044 [P] Update `README.md` com o setup assistido da feature: `uv sync` + `uv run notion-copilot verify`; preparação do board (propriedades de data-model.md — o esqueleto 🔍 é criado pelo orquestrador, ADR-008); habilitação das 3 capabilities; `.env` permissão 600; instalação do scheduler (launchd com `StartInterval: 300`, `ProgramArguments` e `WorkingDirectory` = raiz do projeto; cron `*/5 * * * *` no Linux — research R4); localização do state dir (R3); link para quickstart.md
- [ ] T045 Run the validation scenarios 1–6 from `specs/001-refine-happy-path/quickstart.md` end-to-end against the real board and record the results (inclui auditoria SC-005: responder "o que o agente fez com cada card?" só com board + logs locais)
- [ ] T046 Run the full quality gate and fix findings: `uv run pytest` (núcleo com fakes — RNF-M3), `uv run ruff check .`, `uv run mypy src` — tudo verde
- [ ] T047 [P] Self-review the implementation against the constitution before merge: princípios I–X (em especial III — nenhuma ferramenta de Notion ao agente — e IV — um arquivo por conhecimento externo) e os 14 red flags de Ousterhout; corrigir violações encontradas

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Sem dependências — pode começar imediatamente.
- **Foundational (Phase 2)**: Depende do Setup (T001–T003) — BLOQUEIA todas as user stories.
- **User Stories (Phases 3–5)**: Todas dependem da fase Foundational completa.
- **Polish (Phase 6)**: Depende de todas as user stories desejadas estarem completas (T045 requer US-1/2/3; T044 pode adiantar depois da US-1).

### User Story Dependencies

- **US1 (P1)**: Começa após a Foundational. É o esqueleto vertical (run_round, process_card, adapters Notion/Claude, prompt) — nenhuma dependência de outras stories.
- **US2 (P2)**: Começa após a Foundational; estende `process_card.py` e `rules.py` criados na US-1 (dependência de código), mas é testável de forma independente (cenários 2 da quickstart).
- **US3 (P3)**: Começa após a Foundational; estende `process_card.py`, `run_round.py` e `notion_api.py` da US-1 (dependência de código), testável de forma independente (cenários 3–6 da quickstart).

### Within Each User Story

- Testes primeiro (escritos e FALHANDO antes da implementação — constituição VI).
- Domain antes de application; application antes de adapters/clique (exceto onde o contrário estiver explícito).
- Story completa antes de ir para a próxima prioridade.

### Parallel Opportunities

- T002–T007 (Setup): arquivos distintos, todas [P].
- T008–T012 e T013–T018 dentro da Foundational: testes [P] entre si; `models.py`/`stages.py`/`config.py`/`logging_fs.py`/`lock_fs.py` são arquivos distintos.
- T019–T024 (testes da US-1): todos [P], arquivos distintos.
- T025/T026 (prompt + loader) rodam em paralelo com T019–T024.
- Depois da Foundational, US-2 e US-3 podem ser feitas em paralelo por pessoas diferentes (US-3 toca `run_round.py`; US-2 toca `rules.py`/`process_card.py` — coordenar `process_card.py` que ambas tocam).

---

## Parallel Example: User Story 1

```bash
# Lançar juntos os testes da US-1 (arquivos distintos):
Task T019: tests/unit/domain/test_rules_selection.py
Task T020: tests/unit/domain/test_refine_ops.py
Task T021: tests/unit/application/test_run_round.py
Task T022: tests/unit/application/test_process_card.py
Task T023: tests/integration/test_notion_api.py
Task T024: tests/integration/test_claude_cli.py

# Depois, em paralelo (arquivos distintos):
Task T025: prompts/refine.md
Task T026: src/notion_copilot/adapters/prompts_fs.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — bloqueia todas as stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: quickstart.md cenário 1 (card real em To Refine → Refined refinado)
5. Demo/pronto para uso piloto

### Incremental Delivery

1. Setup + Foundational → fundação pronta
2. US-1 → valida independente → MVP
3. US-2 → valida independente (cenário 2 — idempotência e 📝)
4. US-3 → valida independente (cenários 3–6 — falhas visíveis)
5. Polish → README, validação completa, gates verdes

### Verification Points During Implementation (research, não bloqueiam o design)

- R2 (T028): `notion-client` expõe o endpoint markdown? Se não, REST `client.request` só para este endpoint em `adapters/notion_api.py`.
- R5 (T029): nome exato da credencial (`ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY`) e prefixo das ferramentas MCP — confirmar com `claude mcp list` na máquina.

---

## Notes

- [P] = arquivos diferentes, sem dependências de tasks incompletas.
- [Story] mapeia a task à user story da spec.md para rastreabilidade.
- Cada user story é completável e testável de forma independente.
- Testes do núcleo rodam SEM rede, SEM Notion, SEM modelo (fakes dos ports — RNF-M3).
- Verificar que os testes falham antes de implementar (constituição VI).
- Commit após cada task ou grupo lógico.
- Parar em qualquer checkpoint para validar a story de forma independente.
- Evitar: tasks vagas, conflito no mesmo arquivo, dependências entre stories que quebrem independência.
