# Feature Specification: Refine Happy Path

**Feature Branch**: `001-refine-happy-path`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Fatia vertical MVP da v2: uma rodada completa que processa cards na raia To Refine — do gatilho do scheduler ao card refinado de volta no board, passando pelo agente, pela preservação do registro original e pela escrita da seção de Refinamento. Sem Plan, sem Execute."

## Clarifications

### Session 2026-10-10

- Q: Onde um card fica depois de uma falha de processamento (⚠️ erro) e como ele reentra na fila para ser reprocessado? → A: Card ⚠️ permanece em To Refine, mas excluído da seleção; reentra quando a usuária limpa manualmente o IA status para vazio (a mesma regra vale para ❓: devolver a To Refine e limpar o status).
- Q: Na etapa Refine, o agente recebe alguma ferramenta de leitura do Notion? → A: Não — somente busca web e fetch de páginas web; todo o conteúdo do card é entregue no prompt montado pelo orquestrador.
- Q: O alvo de 15 min / 95% (SC-001) é realista com lotes de até 5 cards sequenciais? → A: Sim, manter como está — lotes cheios são raros no uso real e o threshold de 95% já os acomoda.
- Q: Como o sistema identifica a usuária a mencionar no comentário (FR-014)? → A: NOTION_USER_ID no .env (permissão 600), validado no pré-flight da rodada (FR-002).
- Q: O cenário 5 da US-1 ("ao concluir, volta a vazio") contradiz o FR-012 (terminal ❓) — corrigir? → A: Sim — "ao concluir sem perguntas bloqueantes, volta a vazio; com perguntas bloqueantes, termina ❓ precisa de você (FR-012)".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Refino automático de ponta a ponta (Priority: P1)

Eu movo um card capturado às pressas para a raia **To Refine** e, sem fazer mais nada, o card volta na raia **Refined** com: título curto e claro, o registro original preservado, e uma seção `## 🔍 Refinamento` contendo Contexto, Links guardados, Ações sugeridas, O que já adiantei, Perguntas abertas, Prompt sugerido e Executor sugerido — no nível do exemplo-ouro do PRD (seção 10).

**Why this priority**: É o valor central do produto: capturar rápido e nunca mais esclarecer à mão. Valida o esqueleto inteiro da v2 (gatilho, seleção da fila, agente, escrita, movimentação) no menor risco.

**Independent Test**: Mover um card real (ex.: uma frase solta tipo "ligar pra estacio pra saber como pegar bolsa do curso") para To Refine e observar o board: em minutos o card está em Refined com a seção de refinamento preenchida.

**Acceptance Scenarios**:

1. **Given** um card na raia To Refine com IA status vazio, **When** a rodada iniciar, **Then** o card é selecionado, processado, recebe a seção `## 🔍 Refinamento` na própria página e é movido para Refined.
2. **Given** mais de 5 cards elegíveis em To Refine, **When** a rodada iniciar, **Then** no máximo 5 cards são processados (mais antigos primeiro) e o restante fica para a rodada seguinte.
3. **Given** um card com apenas uma frase de captura, **When** for refinado, **Then** o refinamento distingue Fatos (com fonte), Hipóteses e Perguntas abertas, e todo fato verificado cita a fonte com link.
4. **Given** o agente produz o texto do refinamento, **When** o texto estiver pronto, **Then** quem grava na página do card é o orquestrador — o agente não recebe nenhuma ferramenta de escrita no Notion nesta etapa.
5. **Given** um card em To Refine, **When** o refinamento começar, **Then** o IA status muda para ⏳ rodando antes de qualquer chamada ao agente; ao concluir sem perguntas bloqueantes, volta a vazio; com perguntas bloqueantes, termina ❓ precisa de você (FR-012).

---

### User Story 2 - Registro original preservado (Priority: P2)

Antes de qualquer reescrita do título, o conteúdo original da captura é copiado para um bloco "📝 Registro original" que nunca é editado. Eu posso sempre verificar o que eu realmente escrevi, versus o que o agente interpretou.

**Why this priority**: Confiança. Sem preservação do registro, eu não posso auditar o agente e a reescrita de título se torna uma perda de dados.

**Independent Test**: Criar um card com título confuso, processá-lo e comparar o bloco 📝 com o título original digitado na captura — devem ser idênticos.

**Acceptance Scenarios**:

1. **Given** um card cujo título será reescrito, **When** o refinamento gravar o resultado, **Then** a página contém o bloco "📝 Registro original" com o texto exato da captura, posicionado antes da seção de refinamento.
2. **Given** um card já processado (já tem bloco 📝 e seção 🔍), **When** for processado novamente por engano, **Then** nenhuma segunda seção `## 🔍 Refinamento` nem segundo bloco 📝 é criado (idempotência por card).

---

### User Story 3 - Falha visível e rodada que continua (Priority: P3)

Quando o agente falha, demora demais ou precisa de uma resposta minha, o card para de ser "um mistério rodando": o board mostra ⚠️ erro ou ❓ precisa de você, um comentário na página me notifica com o identificador da execução, e os demais cards da rodada continuam sendo processados normalmente.

**Why this priority**: É a rede de segurança que torna as histórias 1 e 2 confiáveis no uso diário. Sem ela, uma falha congela a fila silenciosamente.

**Independent Test**: Simular um card que causa erro no agente e observar: o card fica ⚠️ com comentário, e um segundo card elegível na mesma rodada é processado até o fim.

**Acceptance Scenarios**:

1. **Given** um card cujo processamento falha, **When** a falha ocorrer, **Then** somente esse card recebe IA status ⚠️ erro; a rodada continua com os demais cards selecionados.
2. **Given** um card cujo refinamento depende de informação que só eu tenho, **When** o agente identificar perguntas bloqueantes, **Then** o card recebe IA status ❓ precisa de você e vai para Refined com as perguntas abertas na seção de refinamento.
3. **Given** uma falha ou bloqueio, **When** o IA status for definido como ⚠️ ou ❓, **Then** a página do card recebe um comentário mencionando a usuária (gerando notificação do Notion) e incluindo o identificador da execução que falhou.
4. **Given** um card em ⏳ rodando há mais de 30 minutos (processo interrompido), **When** a rodada seguinte rodar, **Then** o card é marcado ⚠️ erro.

### Edge Cases

- **Rodadas sobrepostas**: a rodada leva mais de 5 minutos (provável: 5 cards × minutos de agente cada) e o scheduler dispara de novo — a nova rodada NÃO deve iniciar; cards em ⏳ nunca são selecionados duas vezes.
- **Fila vazia**: a rodada acorda, não encontra cards elegíveis e termina com custo mínimo (uma consulta).
- **Laptop dormindo / offline**: nenhuma rodada acontece; quando a máquina volta, a rodada seguinte encontra os cards ainda em To Refine (o estado vive no Notion, nada se perde).
- **Agente excede 10 minutos**: execução interrompida por timeout; card vira ⚠️; nenhum resultado parcial é gravado sem validação.
- **Erro temporário (rede, limite de API)**: até 2 novas tentativas com espera crescente; esgotadas as tentativas, o card vira ⚠️.
- **Card movido de raia durante o processamento**: o resultado só é gravado e o card só é movido se o card ainda estiver onde a rodada o encontrou; caso contrário, nada é escrito.
- **Título já bom**: se o título original já é claro, o agente pode mantê-lo; o bloco 📝 é criado de qualquer forma antes da decisão.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE iniciar uma rodada (processo de vida curta) a cada 5 minutos, via agendador nativo do sistema operacional, sem processo permanente.
- **FR-002**: Cada rodada DEVE validar antes de processar: presença e permissões do arquivo de credenciais, validade do token do Notion (consulta de identidade, sem gastar tokens de modelo), presença do executável do agente e propriedades esperadas do banco. Faltando algo, a rodada DEVE parar com mensagem dizendo o que falta e como corrigir.
- **FR-003**: Enquanto uma rodada estiver em execução, o sistema NÃO DEVE iniciar a rodada seguinte (trava contra rodadas sobrepostas).
- **FR-004**: A seleção da fila DEVE considerar somente cards na raia To Refine com IA status vazio, ordenados por criação, limitados a 5 cards por rodada, um por vez. (Cards que terminaram em ❓ ou ⚠️ só reentram na fila por decisão explícita da usuária: devolvê-los à raia To Refine, quando estiverem em Refined, e limpar o IA status para vazio.)
- **FR-005**: Antes de invocar o agente, o sistema DEVE marcar o card como ⏳ rodando; a seleção nunca DEVE pegar um card em ⏳.
- **FR-006**: Antes de reescrever o título, o sistema DEVE copiar o registro original para um bloco "📝 Registro original" que nunca é editado depois.
- **FR-007**: O sistema DEVE invocar o agente como subprocesso, entregando o prompt da etapa Refine (arquivo versionado) e o conteúdo do card (título, propriedades, corpo), com tempo máximo de execução de 10 minutos por card.
- **FR-008**: Na etapa Refine, o agente DEVE receber somente as ferramentas de busca web e leitura de páginas web (fetch) — nenhuma ferramenta de acesso ao Notion, nem de leitura nem de escrita; todo o conteúdo do card é entregue no prompt pelo orquestrador (FR-007).
- **FR-009**: Quem grava a seção `## 🔍 Refinamento`, o novo título e as mudanças de propriedades DEVE ser o orquestrador, a partir do texto produzido pelo agente — nunca o agente diretamente.
- **FR-010**: O refinamento DEVE seguir o contrato de saída da etapa: Contexto (síntese), Links guardados, Ações sugeridas, O que já adiantei, Perguntas abertas, Prompt sugerido para execução e Executor sugerido; fatos verificados citam fonte com link; fato sem fonte é marcado como Hipótese.
- **FR-011**: Após gravar o resultado com sucesso, o sistema DEVE mover o card para a raia Refined e limpar o IA status.
- **FR-012**: Se o refinamento contiver perguntas bloqueantes, o card DEVE terminar em Refined com IA status ❓ precisa de você.
- **FR-013**: Em falha de processamento, o sistema DEVE marcar somente o card afetado como ⚠️ erro — o card permanece na raia To Refine, excluído da seleção até que a usuária limpe o IA status — e continuar a rodada com os demais cards.
- **FR-014**: Sempre que o IA status for ⚠️ ou ❓, o sistema DEVE deixar um comentário na página do card mencionando a usuária (notificação do Notion) e incluindo o identificador da execução. A usuária é identificada por `NOTION_USER_ID` no `.env` (permissão 600), validado no pré-flight da rodada (FR-002).
- **FR-015**: O processamento de um card DEVE ser idempotente: reprocessar um card não cria segunda seção de refinamento, segundo bloco de registro original, nem altera o bloco 📝 existente.
- **FR-016**: Falhas temporárias DEVEM receber até 2 novas tentativas com espera crescente; esgotadas as tentativas, o card DEVE virar ⚠️ erro.
- **FR-017**: Um card em ⏳ rodando há mais de 30 minutos DEVE ser marcado ⚠️ erro na rodada seguinte.
- **FR-018**: O sistema DEVE gravar cada rodada e cada card em apenas uma das situações de término: sucesso (Refined), precisa de você (Refined + ❓) ou erro (⚠️, permanecendo em To Refine) — nunca deixando um card em ⏳ no fim da rodada, exceto se a rodada inteira for interrompida (caso coberto por FR-017).

### Key Entities *(include if feature involves data)*

- **Card**: uma página-tarefa no board do inbox. Atributos: título, propriedades (Pipeline, Executor, IA status, IA atualizado em), corpo da página. É a unidade de trabalho da fila.
- **Rodada (run)**: uma execução do processo disparada pelo scheduler. Atributos: identificador único (`run_id`), horário de início, cards selecionados, resultado de cada card.
- **Refinamento**: seção de texto gravada na página do card, com contrato fixo de conteúdo (FR-010). Produzida pelo agente, gravada pelo orquestrador.
- **Registro original**: bloco imutável na página do card com o texto exato da captura.
- **IA status**: propriedade do card que comunica o estado do trabalho da IA: vazio (ok), ⏳ rodando, ❓ precisa de você, ⚠️ erro.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um card movido para To Refine é processado e chega a Refined em até 15 minutos em 95% dos casos (latência da rodada + processamento).
- **SC-002**: Nenhum card processado duas vezes cria seção duplicada ou bloco de registro original duplicado (idempotência verificável por inspeção da página).
- **SC-003**: 100% das falhas e bloqueios ficam visíveis no board (⚠️ ou ❓) com comentário notificando a usuária — nenhuma falha silenciosa.
- **SC-004**: Refinamentos de capturas de uma frase só (como o exemplo-ouro) chegam em Refined com todas as seções do contrato preenchidas e fatos com fonte, em pelo menos 80% dos casos em uso real das duas primeiras semanas.
- **SC-005**: A usuária consegue responder "o que o agente fez com cada card?" consultando apenas o board e os logs locais, sem perguntar a ninguém.

## Assumptions

- **Intervalo de 5 minutos** decidido pela usuária (2026-10-10), revendo o ADR-001 (que registrava 15 min). O ADR-001 é imutável: a mudança de intervalo DEVE ser registrada em um novo ADR que o substitui. A proteção contra sobreposição (FR-003) torna o intervalo de 5 min seguro mesmo com rodadas longas.
- Escopo limitado à raia **To Refine**. As raias Plan e AI execute existem no board mas não são lidas por esta feature; viram features seguintes (`plan-approval-gate`, `execute-with-notion-mcp`).
- O comando de instalação completa (`setup`, criação de banco e `.env` interativo, RNF-P5) fica FORA desta feature; assume-se configuração manual assistida (README da feature) durante o desenvolvimento. A instalação self-service é feature própria (`installer-setup`).
- Comentário com menção via API do Notion está no escopo (FR-014) porque é o canal de notificação da usuária.
- A migração dos cards existentes (seção 5.2 do PRD) é operação única de preparação do board, executada manualmente antes do piloto, não parte desta feature.
- O agente roda como subprocesso do Claude Code CLI com endpoint Z.ai, conforme ADR-004; busca web via MCPs da Z.ai (ADR-005); escrita no card via API do Notion (ADR-002, ADR-006 proposto).
- Credenciais no `.env` com permissão 600, nunca em variável global; nenhum log contém segredo.
