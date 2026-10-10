# Research — Refine Happy Path (Phase 0)

**Data**: 2026-10-10 | **Fontes**: docs do projeto (PRD, Design Doc, ADRs 001–006, constituição), spec `001-refine-happy-path`, documentação oficial da API do Notion (developers.notion.com, versão `2026-03-11`), documentação do Claude Code CLI.

Cada item resolve um NEEDS CLARIFICATION do plano ou uma decisão técnica da spec.

---

## R1. Escrita da seção de refinamento: preencher o template da página com `update_content`

**Decisão**: a página do card nasce de um **template do banco do Notion** que já contém o esqueleto da seção de refinamento — o heading `## 🔍 Refinamento — <data>` (data renderizada pelo Notion na criação da página) e os headings vazios `### Contexto`, `### Links guardados`, `### Ações sugeridas`, `### O que já adiantei`, `### Perguntas abertas`, `### Prompt sugerido` e `### Executor sugerido`. O orquestrador **preenche** esse esqueleto com o comando oficial `update_content` do endpoint `PATCH /v1/pages/{page_id}/markdown` (API `2026-03-11`): uma operação por seção, com `old_str` = heading do template (ex.: `### Contexto`) e `new_str` = heading + corpo produzido pelo agente. O bloco 📝 Registro original é inserido pela mesma mecânica — `old_str` = `## 🔍 Refinamento`, `new_str` = `📝 Registro original + texto exato da captura + ## 🔍 Refinamento` — o que o posiciona **antes** da seção de refinamento, como exige a US-2. Orquestrador e agente não criam nem alteram o heading com data: ele vem do template.

**Rationale**: `update_content` é o comando **recomendado** pela documentação oficial (reference/update-page-markdown); `insert_content` e `replace_content_range` estão classificados como **legacy** — decisão da usuária (2026-10-10): adotar o comando atual desde já, sem migração pendente. O formato enhanced markdown (default, `markdown_version: v1`) cobre o corpo das seções do contrato FR-010 (parágrafo, bulleted/numbered list, to-do `- [ ]`, quote, código, bold/itálico/inline e links). O template pré-existente resolve a data do heading e simplifica o contrato do agente: ele devolve apenas os **corpos** das seções, nunca headings (ver `contracts/agent-output.md`). Requer as capabilities **Read content** (o `GET .../markdown` da idempotência, R9) e **Update content** (o `update_content`) na conexão — sem elas a API retorna 403; viram passo de setup e verificação no pré-flight (FR-002), junto com a capability de comentários (R6).

**Alternativas consideradas**:
- `insert_content` com `position: start/end` (legacy): funcionaria para escrita aditiva, mas mantém comando marcado como legacy — rejeitado (decisão da usuária: comando atual desde já).
- `replace_content` (substituição total da página): rejeitado — conflitaria com o registro original e com conteúdo pré-existente do card.
- Conversor markdown→blocks próprio + `PATCH /v1/blocks/{id}/children` (decisão de uma versão anterior desta research): desnecessário — a API faz a conversão server-side; manter o conversor seria reescrever código da plataforma (YAGNI, constituição VIII).

**Consequências**: escrita em um único request (o endpoint aceita até 100 operações; esta feature usa 8 — sete seções + bloco 📝). Cada `old_str` deve casar **exatamente uma vez**: os headings do template são únicos na página e o contrato do agente proíbe headings dentro dos corpos, para não criar casamentos ambíguos. Card criado **sem** o template (heading ausente) falha com erro permanente e visível (⚠️) — nunca com escrita silenciosa no lugar errado. Página grande demais (~20.000 registros) retorna `validation_error` permanente (não repete — R8); `allow_async: true` fica registrado como escape. O template do banco vira pré-requisito de setup (quickstart) e as capabilities entram no `verify` (R2/R6, `contracts/cli-commands.md`).

---

## R2. Cliente da API do Notion

**Decisão**: usar o SDK oficial `notion-client` (Python), encapsulado exclusivamente em `adapters/notion_api.py`.

**Rationale**: SDK oficial mantido pela Notion, cobre endpoints necessários (`databases.query`, `pages.retrieve/update`, `comments.create`, `users.me` para o pré-flight FR-002). Encapsulamento mantém o invariante constitucional de que só um arquivo conhece o formato da API do Notion.

**Ponto de verificação em implementação**: os exemplos oficiais do endpoint markdown (R1) mostram o SDK TypeScript (`pages.updateMarkdown`); confirmar se `notion-client` (Python) já expõe o endpoint. Se não, chamada REST direta (`httpx` ou `client.request`) **apenas para este endpoint**, encapsulada em `adapters/notion_api.py` — o restante permanece no SDK.

**Alternativas consideradas**: `httpx` puro para tudo (mais controle, porém reescreve retry/paginação/versão de API sem ganho — rejeitado).

---

## R3. Trava contra rodadas sobrepostas (FR-003)

**Decisão**: lockfile local com `fcntl.flock` (Linux/macOS) em diretório de estado (ex.: `~/.local/state/notion-copilot/round.lock`, ou `~/Library/Application Support/notion-copilot/` no macOS via `platformdirs`). `run_round` adquire no início e libera em `try/finally`. Se o lock estiver ocupado, a rodada termina com exit code próprio e custo zero de API. O mesmo diretório de estado — resolvido com `platformdirs` (dependência declarada no plano) e guardado em `config.py` como caminho absoluto — também recebe os logs locais (eventos JSON e rastro `stream-json`); nada depende do diretório de trabalho do scheduler.

**Rationale**: a API do Notion não oferece compare-and-swap atomico em propriedades — um lock via Notion teria corrida. O scheduler roda numa única máquina (1 usuária), então lock local é suficiente e é o mecanismo mais simples que funciona.

**Alternativas consideradas**: lock via propriedade no board (rejeitado: race entre consulta e escrita); PID file manual (rejeitado: `flock` é atomico e liberado pelo SO em crash).

**Nota**: a defesa em profundização continua sendo o IA status ⏳ (FR-005): a seleção nunca pega card em ⏳, então mesmo sem lock dois processos não processariam o mesmo card.

---

## R4. Scheduler a cada 5 minutos (FR-001)

**Decisão**: launchd (macOS) com `StartInterval: 300`, `ProgramArguments: [uv, run, notion-copilot, run]` **e `WorkingDirectory` = raiz do projeto** — o diretório de trabalho default do launchd é `/`, o que quebraria `uv run` (que procura o `pyproject.toml`) e qualquer caminho relativo; cron (`*/5 * * * *`) no Linux, com o mesmo cuidado de caminhos absolutos no crontab. Instalação do plist/crontab documentada no README da feature (setup assistido; feature `installer-setup` fica fora do escopo).

**Rationale**: ADR-001 (cron/launchd, processo curto). O intervalo muda de 15 → 5 min por decisão da usuária (2026-10-10); ADR-001 é imutável, portanto a feature cria o **ADR-007** registrando a troca. A segurança do intervalo menor vem do lock (R3) e do ⏳ (FR-005).

**Alternativas consideradas**: manter 15 min (rejeitado pela usuária); daemon com polling interno (rejeitado no ADR-001).

---

## R5. Invocação do agente (Claude Code CLI + Z.ai)

**Decisão**: subprocesso `claude -p "<prompt montado>" --output-format stream-json --verbose --allowedTools "mcp__web_search_prime" "mcp__web_reader" --mcp-config .mcp.json --max-turns <N> --model <modelo>` com env `ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic` e credencial passada **somente ao subprocesso** (nunca variável global — RNF-S6). Timeout de 10 min via `subprocess` (RNF-C4). O rastro `stream-json` completo é salvo por execução (RNF-O3). O parse das flags e do stream fica só em `adapters/claude_cli.py`. O caminho do `.mcp.json` é resolvido como absoluto em `config.py` — launchd/cron executam fora do diretório do projeto (ver R4).

**Rationale**: ADR-004 (CLI como runtime, sem loop próprio) e ADR-005 (MCPs da Z.ai). `--allowedTools` com allowlist garante por configuração que o agente não recebe ferramenta de Notion nem de escrita (constituição III, FR-008) — a segurança é por ausência, não por prompt.

**Alternativas consideradas**: agentic loop próprio (rejeitado, ADR-004); WebSearch nativa (rejeitada, ADR-005 — disponibilidade no endpoint Z.ai não garantida).

**Ponto de verificação em implementação** (não bloqueia o design): nome exato da variável de credencial exigida pelo CLI no endpoint Z.ai (`ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY`) e o prefixo exato das ferramentas MCP no `--allowedTools` — confirmar com `claude mcp list` na máquina da usuária e fixar no `config.py`.

---

## R6. Comentário com menção e notificação (FR-014)

**Decisão**: `POST /v1/comments` com `parent.page_id` e `rich_text` = [mention de user (`NOTION_USER_ID` do `.env`) + texto com `run_id`]. Requer que a integração tenha a **capability de inserir comentários habilitada** (vem desligada por padrão — sem ela a API retorna 403). Isso vira: (a) passo documentado no README de setup; (b) verificação no `verify`/pré-flight (FR-002) — tentativa de comentário de prova ou leitura das capabilities.

Verificado na API reference: o endpoint aceita `rich_text` com Mention de user e também corpo em `markdown` (inline). Menções disparam notificação do Notion por padrão (não usar `notifications.mode: silent` nas escritas).

**Alternativas consideradas**: e-mail/notificação externa (rejeitada — o board é a interface); comentário sem menção (rejeitado — não gera notificação).

---

## R7. Seleção da fila, elegibilidade, varredura de abandonados e regra dos 30 min

**Decisão**: `databases.query` com filtro `Pipeline = "To Refine"` AND `IA status is empty`, ordenado por `created_time` asc, `page_size: 5` (FR-004, ADR-003). Cards ⚠️/❓ ficam automaticamente fora (status não vazio) e só reentram por ação manual da usuária (limpar status + devolver a To Refine). Antes da seleção, uma **segunda query varre os abandonados** (FR-017): `Pipeline = "To Refine"` AND `IA status = ⏳` AND `IA atualizado em < agora − 30 min` → cada card encontrado é marcado ⚠️ erro com comentário (FR-014) e não entra na seleção. `is_stale` (⏳ há > 30 min) vive em `domain/rules.py`, comparando `IA atualizado em` com o port `Clock`; o invariante correspondente — `IA atualizado em` é reescrito a cada transição de IA status — está no data-model.

**Rationale**: a coluna é a fila (ADR-003); filtro server-side minimiza custo (fila vazia = 1 request).

---

## R8. Retry com backoff (FR-016)

**Decisão**: laço manual no `process_card`: até 2 novas tentativas em erros temporários (rede, 429/5xx do Notion, timeout do agente) com espera crescente (ex.: 30s, 120s — valores em `config.py`). Erros permanentes (validação do JSON do agente, 4xx) não repetem. Sem dependência (tenacity rejeitado — YAGNI, constituição VIII).

---

## R9. Idempotência por card (FR-015, SC-002)

**Decisão**: antes de escrever, o orquestrador lê a página via `GET /v1/pages/{page_id}/markdown` e avalia **dois marcadores independentes**: (a) `has_original_record` — a página contém o bloco "📝 Registro original"; (b) `has_refinement` — alguma seção do template (ex.: `### Contexto`) já tem corpo não-vazio entre ela e o heading seguinte. Cada marcador pula **somente a sua** escrita: 📝 existente → não cria segundo 📝 nem altera o existente; seção já preenchida → não é reescrita. Um card que recebeu 📝 mas morreu antes do preenchimento (timeout, crash) tem, na reexecução, o 📝 preservado e as seções preenchidas — nunca é movido para Refined sem refinamento. O template entrega o heading 🔍 desde a criação, portanto o heading sozinho **não** serve de marcador. Os checks vivem em `domain/rules.py` (recebem a string markdown já buscada pelo adapter — domain não conhece o formato Notion).

**Alternativas consideradas**: flag em propriedade (rejeitada: pode divergir do conteúdo real da página; a página é a verdade); marcador único "heading 🔍 existe" (rejeitado: o template o torna sempre verdadeiro — não distingue card refinado de card recém-criado).

---

## R10. Card movido durante o processamento (edge case da spec)

**Decisão**: imediatamente antes de gravar, o orquestrador relê as propriedades do card; grava/move somente se `Pipeline` continuar sendo o mesmo da seleção. Caso contrário, não escreve nada e registra evento `card_moved_during_processing` (card volta a status vazio, sem efeitos).

---

## R11. Detecção de perguntas bloqueantes (FR-012)

**Decisão**: o contrato JSON do agente (ver `contracts/agent-output.md`) traz `blocking_questions: []` explicitamente. Quem decide se o card termina vazio ou ❓ é o **código** (constituição I): se `blocking_questions` não vazio → Refined + ❓ + comentário com menção (FR-014).

**Alternativas consideradas**: inferir do texto do refinamento (rejeitado — regra em prompt, não em código).

---

## R12. Versão do Python e ferramentas

**Decisão**: Python 3.12+ (pin em `.python-version`), `uv` para ambiente/dependências (`uv.lock` como verdade), `ruff` (lint+format), `mypy` (tipos em `domain/`+`application/`), `pytest`. Type hints obrigatórios no código novo do núcleo (constituição, Workflow de Desenvolvimento).

---

## Resumo de consequências para ADRs

- **ADR-006 (promoção a Aceito)**: a premissa factual ("a API aceita markdown, sem conversão para blocos") foi confirmada na documentação oficial (R1). O ADR-006 está em status **Proposto**; promovê-lo a Aceito é tarefa da feature (tasks.md), citando a R1 como evidência.
- **ADR-007 (novo, obrigatório)**: intervalo 15 → 5 min. Deve substituir também a frase do ADR-001 que dizia que a rodada seguinte seleciona cards com IA status "vazio, ❓ ou ⚠️" — o FR-004 é mais estrito (somente vazio).
- Nota histórica: a primeira versão desta research pedia uma "correção factual" do ADR-006 com base na premissa errônea de que a API não aceita markdown em páginas; a verificação na documentação oficial (R1) mostrou o contrário.
