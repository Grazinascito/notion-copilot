# Quickstart — Validação end-to-end (Refine Happy Path)

Guia de validação da fatia vertical: mover um card real para To Refine e vê-lo voltar em Refined refinado. Os detalhes de entidades e estados estão em [data-model.md](./data-model.md); os contratos de entrada/saída em [contracts/](./contracts/).

## Pré-requisitos

- Python 3.12+ e `uv` instalados;
- Claude Code CLI instalado e autenticado com o endpoint Z.ai (research R5);
- Integração Notion com: acesso ao banco do inbox, capabilities **Read content**, **Update content** e **Insert comments** habilitadas (research R1/R6), páginas compartilhadas com a integração;
- `.env` (permissão 600) com `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `NOTION_USER_ID` e credencial do modelo — copiar de `.env.example`;
- Board do inbox com as propriedades de [data-model.md](./data-model.md) e o **template de página** com o esqueleto `## 🔍 Refinamento` e os headings vazios das 7 seções do contrato, incluindo `### Prompt sugerido` (research R1); migração da seção 5.2 do PRD já executada manualmente.

## Setup

```bash
uv sync                        # instala Python e dependências exatas do uv.lock
uv run notion-copilot verify   # pré-flight: tudo ✔ antes de prosseguir (FR-002)
```

## Cenários de validação

### 1. Happy path (US-1)

1. Criar card com uma frase solta, ex.: *"ligar pra estacio pra saber como pegar bolsa do curso"*, em To Refine, IA status vazio.
2. Aguardar a rodada (ou forçar: `uv run notion-copilot run`).
3. **Esperado**: card em **Refined**, IA status vazio; página com bloco 📝 (texto exato da captura) **antes** da seção `## 🔍 Refinamento`, com as 7 seções do template **preenchidas** — o esqueleto vem do template do banco, o orquestrador só preenche ([contracts/agent-output.md](./contracts/agent-output.md)); fatos com fonte linkada; título curto novo. Qualidade comparável ao exemplo-ouro (PRD §10). Latência ≤ 15 min (SC-001).

### 2. Registro original preservado (US-2)

- Comparar o bloco 📝 com o texto digitado na captura: **idênticos**.
- Reexecutar o processamento (ex.: limpar status e devolver a To Refine): nenhuma seção é reescrita e não surge segundo bloco 📝; o heading 🔍 continua o do template; o card termina em **Refined** com IA status vazio — desfecho `skipped_already_refined` (FR-015, SC-002, R9).

### 3. Falha visível e rodada que continua (US-3)

- Colocar 2 cards elegíveis; fazer um deles falhar (ex.: credencial do modelo inválida temporariamente, ou card que induz erro).
- **Esperado**: só o card afetado fica ⚠️ (em To Refine, excluído da seleção); comentário na página mencionando a usuária (notificação chega) com `run_id`; o outro card é processado até o fim (FR-013, SC-003).

### 4. Perguntas bloqueantes (US-3.2)

- Card cujo refinamento dependa de informação só da usuária.
- **Esperado**: card em Refined com IA status ❓ e comentário com menção + `run_id` (FR-012/FR-014).

### 5. Fila e limites

- 6+ cards elegíveis: rodada processa 5 (mais antigos primeiro); o 6º fica para a seguinte (FR-004).
- Rodar duas rodadas em paralelo (`uv run notion-copilot run & uv run notion-copilot run`): a segunda termina com exit 2 e **não** processa nada (FR-003).
- Fila vazia: rodada termina em segundos com custo de 1 consulta (edge case).

### 6. Timeout e abandono

- Agente exceder 10 min → interrompido, card ⚠️ **sem retry** (decisão 2026-10-10 — research R8), nada gravado sem validação (edge case).
- Card em ⏳ há > 30 min (simular `IA atualizado em`) → marcado ⚠️ na rodada seguinte (FR-017).

## Testes automatizados

```bash
uv run pytest          # núcleo com fakes dos ports (sem rede, sem Notion, sem modelo — RNF-M3)
uv run ruff check .    # lint
uv run mypy src        # tipos
```

Os testes do núcleo cobrem: seleção/elegibilidade, idempotência (marcadores independentes — R9), transições de IA status, `is_stale`, retry/backoff, parsing+validação do JSON do agente e dos corpos de seção do contrato (`contracts/agent-output.md`).

## Auditoria (SC-005)

Após os cenários, responder "o que o agente fez com cada card?" consultando apenas o board e os logs locais no diretório de estado (research R3 — eventos JSON por `run_id`/`card_id` + rastro `stream-json`), sem acesso externo.
