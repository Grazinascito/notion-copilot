# Notion Copilot — Architecture Decision Records (ADRs)

> ADR (*Architecture Decision Record*) é um documento curto que registra uma decisão de arquitetura: o contexto, as opções consideradas, a decisão e suas consequências. Cada ADR é imutável depois de aceito; para mudar uma decisão, cria-se um novo ADR que o substitui.

| # | Decisão | Status |
|---|---|---|
| ADR-001 | Gatilho: cron/launchd com processo de vida curta | ✅ Aceito (intervalo e seleção: ver ADR-007) |
| ADR-002 | Acesso ao Notion: API para mecânica, MCP para execução aberta | ✅ Aceito |
| ADR-003 | Fila: a coluna "To Refine" é a fila, sem broker | ✅ Aceito |
| ADR-004 | Agent runtime: Claude Code CLI, sem loop próprio | ✅ Aceito |
| ADR-005 | Busca na web: MCP servers da Z.ai | ✅ Aceito |
| ADR-006 | Escrita do resultado: API no Refine/Plan, MCP no Execute | ✅ Aceito |
| ADR-007 | Intervalo do scheduler: 5 minutos; seleção somente IA status vazio | ✅ Aceito |

---

## ADR-001 — Gatilho: cron/launchd com processo de vida curta

**Status:** Aceito (2026-10-04) — intervalo e regra de seleção substituídos pelo ADR-007 (2026-10-10)

**Contexto**

O agente precisa iniciar trabalho quando existem cards na coluna "To Refine". O programa roda no computador da usuária (macOS hoje, Linux para quem clonar o repositório), que é um laptop: dorme, fecha tampa, fica offline. O estado de verdade do pipeline vive no Notion (propriedades Pipeline e IA status).

O evento "card entrou em To Refine" acontece dentro do processo do Notion, nos servidores deles. Para que esse evento dispare código nosso, o dado precisa atravessar a internet até o processo do nosso programa. Existem três primitivos de transporte, e todos os padrões de EDA (Pub/Sub, Event Bus, streaming) são construídos sobre eles:

1. **Pull (polling)** — nosso processo pergunta periodicamente. Não exige infraestrutura.
2. **Push (webhook)** — o Notion chama um endpoint nosso. Exige servidor com HTTPS público.
3. **Conexão persistente (WebSocket/SSE)** — mantemos uma conexão aberta e os eventos escorrem por ela. Exige processo rodando 24/7 (daemon).

**Opções consideradas**

| Opção | Veredito | Motivo da rejeição |
|---|---|---|
| Webhook do Notion (beta) | Rejeitada | Exige endpoint público (quebra "roda no computador de quem clonar"); evento é *edge-triggered* e se perde com o laptop offline; exigiria polling de reconciliação de qualquer forma |
| Conexão persistente | Rejeitada | Exige daemon; a API pública do Notion não expõe endpoint de streaming |
| Daemon com polling interno | Rejeitada | Custo de gerenciar ciclo de vida de processo, sem benefício para um requisito de latência de horas/dias |
| GitHub Actions agendado | Rejeitada | Segredos na nuvem, máquina terceira para depurar |
| Gatilho manual (`copilot run`) | Rejeitada | Depende da usuária lembrar de rodar — reproduz o problema que o projeto resolve |
| Pub/Sub com broker (RabbitMQ, Kafka) | Rejeitada | O broker resolve desacoplamento, não transporte: o consumo ainda é pull ou push. Exigiria infraestrutura própria ou que o Notion publicasse em um broker (não publica) |

**Decisão**

Cron (Linux) ou launchd (macOS) executa um processo de vida curta a cada **15 minutos**. O processo consulta a Notion API, processa até 5 cards e termina. O intervalo de 15 min (não 5) reflete a duração real de uma rodada (subprocesso do Claude Code + busca web = minutos por card; uma rodada pode levar 10–20 min).

Proteção contra rodadas sobrepostas: antes de processar um card, o script grava IA status = ⏳. A rodada seguinte só seleciona cards com IA status vazio, ❓ ou ⚠️.

**Consequências**

- Positivas: zero infraestrutura; estado vive só no Notion; rodadas falhas não perdem trabalho (polling é *level-triggered*: o estado continua lá); fácil de testar rodando o comando manualmente; instalação de uma linha para quem clona.
- Negativas: latência de até 15 min entre mover o card e o processamento (irrelevante perto da meta de "nenhum card parado > 7 dias"); a maioria das rodadas acorda, vê fila vazia e termina (custo: 1 chamada de API por rodada, desprezível).

---

## ADR-002 — Acesso ao Notion: API para mecânica, MCP para execução aberta

**Status:** Aceito (2026-10-04)

**Contexto**

O sistema tem dois consumidores do Notion: (a) o orquestrador Python, que precisa de operações mecânicas e confiáveis (polling, mudar IA status, mover coluna, anexar seções com formato fixo); (b) o agente, que precisa de trabalho aberto e variável por card (criar página em outro banco, editar notas — fase Execute). A API do Notion já aceita markdown, sem conversão para blocos.

Princípio norteador (verificado na literatura e em avaliação empírica — ver referência): **toda operação que deve acontecer igual toda vez, em código; toda operação que depende de interpretar linguagem, no modelo.** Operações via MCP colocam o modelo como decisor de cada chamada: custo de tokens por chamada, seleção ambígua de ferramentas, falhas não reproduzíveis.

**Decisão**

- **Orquestrador é o dono do pipeline.** O agente é uma ferramenta que o orquestrador invoca, não o contrário. A máquina de estados do pipeline (coluna → próxima coluna, regras de desvio, trava de aprovação) vive em código Python, testável, não em prompts.
- **Operações mecânicas via API direta**, no módulo `notion_gateway`: polling, IA status, movimentação de coluna, preservação do registro original, escrita das seções `## 🔍 Refinamento` e `## 🗺️ Plano`.
- **Trabalho aberto via MCP do Notion**, ativado somente na fase Execute.
- **Allowlist de ferramentas por fase.** Na fase Refine o agente não recebe nenhuma ferramenta de escrita no Notion: o orquestrador entrega o conteúdo do card, o agente devolve texto, o orquestrador grava. Regras de segurança (seção 9 do PRD) são garantidas por ausência da ferramenta, não por instrução de prompt.
- Restrição adicional do MCP herdada da literatura: minimizar o conjunto de ferramentas ativo por fase, para reduzir seleção ambígua.

**Consequências**

- Positivas: regras de segurança em código são garantias (regra em prompt é esperança); custo mínimo de tokens nas operações mecânicas; pipeline testável com testes unitários comuns; gasto com modelo só quando existe trabalho real.
- Negativas: dois mecanismos de acesso ao Notion (API no orquestrador + MCP no agente) — complexidade aceita em troca de controle.

**Referência:** avaliação empírica citada na conversa de design (substituição do GitHub MCP por função direta em pipeline de produção, com ganho de determinismo e auditabilidade).

---

## ADR-003 — Fila: a coluna "To Refine" é a fila, sem broker

**Status:** Aceito (2026-10-04)

**Contexto**

Volume máximo de 5 cards por rodada, 4 rodadas por hora. A pergunta era se o projeto precisa de uma fila técnica (Celery, Redis, RabbitMQ).

**Decisão**

Não usar fila técnica. A coluna "To Refine" do Notion **é** a fila: a seleção é um filtro por propriedade (Pipeline = "To Refine", IA status elegível), ordenada por criação, limitada a 5 itens por rodada.

**Consequências**

- Positivas: um componente a menos para instalar, rodar e manter (crítico para um projeto open source de portfólio); o estado da fila é visível para a usuária no próprio board.
- Negativas: sem garantias de entrega, retentativas e ordenação estrita — desnecessárias neste volume. Se o volume crescer ordens de grandeza no futuro, revisitar.

---

## ADR-004 — Agent runtime: Claude Code CLI, sem loop próprio

**Status:** Aceito (2026-10-04)

**Contexto**

O agentic loop (enviar mensagens + tool definitions → receber resposta → executar tool call via registry → anexar tool result → repetir até resposta final), o registry, a validação de schema e o cliente MCP são infraestrutura commodity: resolvidos, padronizados e sem diferencial competitivo. O diferencial do projeto está nas camadas acima (pipeline, gates de aprovação, contrato das fases) e abaixo (integração Notion).

**Decisão**

Usar o Claude Code CLI configurado com o endpoint da Z.ai (`https://api.z.ai/api/anthropic`) como agent runtime, invocado como subprocesso pelo orquestrador. Não escrever loop próprio na v2.

O que o projeto escreve: orquestrador (`notion_copilot`), `notion_gateway`, prompts por fase (versionados no repo), configuração de MCP servers (`.mcp.json`).
O que o projeto não escreve: agentic loop, parser de tool_use, registry, validação de schema, cliente MCP.

**Consequências**

- Positivas: semanas de infraestrutura poupadas; manutenção do protocolo delegada ao fornecedor.
- Negativas: dependência dos limites do Claude Code (telemetria por tool call, controle fino de custo por card). Cenário futuro de runtime próprio registrado como trabalho futuro, não como escopo da v2.

---

## ADR-005 — Busca na web: MCP servers da Z.ai

**Status:** Aceito (2026-10-04)

**Contexto**

A fase Refine precisa pesquisar (o exemplo-ouro da seção 10 do PRD exige fatos com fonte). Busca é trabalho de julgamento (o que pesquisar, quais resultados valem leitura) — portanto competência do agente, não do orquestrador. A v1 já usa os MCP servers `web_search_prime` e `web_reader` da Z.ai com a mesma API key do modelo: compatibilidade comprovada na prática (a qualidade da integração, não — a v1 foi vibecoded e a v2 reconstrói).

**Opções consideradas**

| Opção | Veredito | Motivo |
|---|---|---|
| WebSearch nativa do Claude Code | Rejeitada | Ferramenta server-side da Anthropic; disponibilidade pelo endpoint da Z.ai não garantida |
| MCP servers da Z.ai | **Escolhida** | Compatível com o plano atual; uma única credencial (nenhum cadastro extra para quem clona); provada na v1 |
| MCP de terceiros (Tavily, Brave) | Rejeitada | Cadastro e API key adicional para quem clona |
| Função direta própria sobre API de busca | Rejeitada | Infraestrutura commodity (mesmo argumento do ADR-004) |

**Decisão**

Usar `web_search_prime` (busca) e `web_reader` (leitura de URL) da Z.ai, autenticados com a mesma API key do modelo. Ativados nas fases Refine e Execute. A configuração de busca permanece plugável: quem usar outro provedor troca a configuração do MCP, não código.

Citação de fontes é contrato de saída da fase (prompt versionado): todo fato verificado cita a fonte com link; fato sem fonte vira "Hipótese".

**Consequências**

- Positivas: zero configuração extra para clonadores usando Z.ai; sem código de infraestrutura de busca.
- Negativas: acoplamento de conveniência à Z.ai — mitigado pela configuração plugável.

---

## ADR-006 — Escrita do resultado: API no Refine/Plan, MCP no Execute

**Status:** Aceito (2026-10-10)

**Evidência (2026-10-10):** a premissa "a API do Notion aceita markdown, sem conversão para blocos" foi confirmada na documentação oficial da versão `2026-03-11`: endpoints `GET`/`PATCH /v1/pages/{page_id}/markdown`, com o comando `update_content` recomendado para edição (`insert_content` é legacy) — research R1 da feature `001-refine-happy-path`.

**Contexto**

Deriva direta do ADR-002. Onde cada escrita acontece:

**Decisão proposta**

| Escrita | Quem escreve | Via |
|---|---|---|
| Bloco "📝 Registro original" (preservação) | Orquestrador | API |
| Título novo do card | Orquestrador | API |
| Seção `## 🔍 Refinamento` | Orquestrador (texto produzido pelo agente) | API |
| Seção `## 🗺️ Plano` | Orquestrador (idem) | API |
| Mudanças de Pipeline e IA status | Orquestrador | API |
| Páginas novas/editadas em outros bancos (fase Execute) | Agente | MCP do Notion |
| Seção `## ✅ Resultado` na página do card | Orquestrador (texto produzido pelo agente) | API — mantém formato uniforme entre fases |

A API do Notion aceita markdown, então as seções são anexadas sem conversão para blocos.

**Consequências**

- Positivas: formato uniforme e auditável das seções; invariante "agente não escreve no card" válida em todas as fases exceto Execute.
- Negativas: nenhuma identificada até agora.

---

## ADR-007 — Intervalo do scheduler: 5 minutos; seleção somente IA status vazio

**Status:** Aceito (2026-10-10)

**Contexto**

O ADR-001 fixou o intervalo do gatilho em 15 minutos, com base na duração estimada de uma rodada, e definiu que a rodada seguinte seleciona cards com IA status "vazio, ❓ ou ⚠️". Duas mudanças vieram com a feature `001-refine-happy-path` (2026-10-10):

1. A usuária decidiu reduzir o intervalo para 5 minutos, para atender o critério SC-001 (card em Refined em até 15 minutos em 95% dos casos).
2. A especificação (FR-004) é mais estrita que o ADR-001 na seleção: somente cards em To Refine com IA status **vazio**. Cards em ❓ ou ⚠️ reentram na fila somente por ação manual da usuária (devolver a To Refine e limpar o status) — nunca por seleção automática.

O ADR-001 é imutável; este ADR o substitui nesses dois pontos. O restante do ADR-001 (cron/launchd, processo de vida curta, sem daemon) permanece válido.

**Decisão**

launchd (macOS, `StartInterval: 300`) ou cron (Linux, `*/5 * * * *`) executa `uv run notion-copilot run` a cada 5 minutos (FR-001). A seleção considera somente cards em To Refine com IA status vazio (FR-004).

A segurança do intervalo menor vem de duas proteções que o ADR-001 não tinha:

- **Lock local por rodada** (FR-003, research R3): enquanto uma rodada executa, a seguinte termina imediatamente sem processar nada — rodadas sobrepostas deixam de ser problema.
- **IA status ⏳** (FR-005): a seleção nunca pega um card em processamento; mesmo sem lock, dois processos não processariam o mesmo card.

**Consequências**

- Positivas: a espera máxima entre mover o card e a rodada cai de até 15 para até 5 minutos; filas cheias esvaziam mais rápido (até 5 cards por rodada, ~4 rodadas/hora).
- Negativas: 3 rodadas a mais por hora que acordam com fila vazia (custo: 1 consulta de API cada, desprezável — research R7); rodadas sobrepostas passam a ser o caso comum, cobertas pelo lock.
