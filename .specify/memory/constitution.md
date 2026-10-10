<!--
SYNC IMPACT REPORT (remover antes do commit)
- Version change: (template) → 1.0.0; 1.0.0 → 1.0.1 (remoção de frases retóricas,
  sem mudança normativa)
- Ratificação inicial: constituição derivada do template + PRD + Design Doc + ADRs 001–006.
- Modified principles: nenhum (primeira ratificação).
- Added sections:
  - Core Principles (10 princípios)
  - "Red Flags de Design (Ousterhout, 2019)" — os 14 red flags como regras constitucionais (RNF-M6)
  - "Segurança e Governança do Agente"
  - "Workflow de Desenvolvimento e Qualidade (Python)"
  - Governance
- Removed sections: nenhum.
- Follow-up TODOs: nenhum placeholder pendente.
-->

# Notion Copilot Constitution

## Core Principles

### I. Regras em Código, Não em Prompt (NON-NEGOTIABLE)

Toda operação que deve acontecer igual toda vez DEVE estar em código Python
testável; toda operação que depende de interpretar linguagem PODE estar no
modelo. A máquina de estados do pipeline (transição de raia, trava de
aprovação, idempotência) vive em `domain/`, nunca em prompts (ADR-002,
RNF-S3). Quem decide se um plano precisa de aprovação é o código, nunca
o agente.

### II. Arquitetura Hexagonal com Núcleo Puro

O código DEVE ficar em camadas (`domain` → `application` → `adapters`/`cli`)
com dependências apontando apenas para o núcleo. `domain/` NÃO DEVE importar
nada de Notion, Claude Code, `.env` ou qualquer IO — zero dependências
externas. `application/` declara ports (Protocols); adapters implementam.
Teste prático obrigatório: `domain/` deve ser compreensível sem saber que
Notion e Claude Code existem, e os testes do núcleo DEVEM rodar sem acessar
Notion nem modelo (RNF-M1, RNF-M3).

### III. Segurança por Ausência de Ferramenta (NON-NEGOTIABLE)

Cada etapa do agente DEVE receber somente os servidores MCP e ferramentas de
que precisa (allowlist por fase, RF-15). Nenhuma etapa além do Execute recebe
ferramenta de escrita no Notion; nenhuma ferramenta disponível ao agente DEVE
ser capaz de apagar ou arquivar — garantia de configuração e código, não de
prompt (RNF-S1, RNF-S2). O agente propõe ações em JSON; quem executa é o
orquestrador, que valida com Pydantic antes de escrever.

### IV. Módulos Profundos, Informação Escondida

Cada módulo DEVE ter interface simples e funcionalidade substancial (módulo
profundo). Um arquivo por conhecimento externo: `adapters/notion_api.py` é o
único que sabe o que é um "block" do Notion; `adapters/claude_cli.py` é o
único que sabe o que é stream-json e as flags do CLI. Conhecimento que
atravessa fronteiras DEVE estar em um único lugar (information hiding).
Interfaces expõem o que o consumidor precisa; detalhes de implementação
ficam escondidos.

### V. Aprovação Humana Antes de Ação Irreversível

O agente NUNCA apaga nada. Criar página em outro banco ou editar página fora
do inbox EXIGE aprovação prévia declarada no Plano; sem aprovação, o card
para em ❓. O registro original do card DEVE ser preservado em bloco que
nunca é editado. Toda escrita fora do card DEVE ser registrada em log com
`run_id`, `card_id`, página alterada e tipo de ação (PRD 7.3–7.4, RNF-S5).

### VI. Test-First no Núcleo

Testes automatizados são OBRIGATÓRIOS para: regra de aprovação (RNF-S3),
idempotência (RNF-C1) e transição de raias — sempre contra fakes dos ports,
sem rede. Correr os testes do núcleo também comprova a pureza do `domain/`.
Todo bug corrigido no núcleo DEVE ganhar teste de regressão (RNF-M3).

### VII. Observabilidade Estruturada

Cada evento DEVE ser uma linha JSON com horário, `run_id`, `card_id`, etapa,
evento e duração (RNF-O1/O2). Cada execução do agente DEVE salvar o rastro
completo de tool calls (`stream-json`, RNF-O3). Nenhum log DEVE conter API
key ou token (RNF-O5). Teste de prontidão: a pergunta "o que o agente mudou
no workspace na semana passada?" DEVE ser respondível usando só os logs
(RNF-S5).

### VIII. Simplicidade e YAGNI

A coluna do Notion é a fila — sem broker, sem daemon, sem endpoint público,
sem serviços pagos (ADR-001, ADR-003). Começar simples: nenhuma dependência
ou componente DEVE entrar sem uma necessidade concreta do presente.
Complexidade acidental DEVE ser justificada por escrito (design doc ou ADR).

### IX. Comportamento como Artefato Versionado

O prompt de cada etapa DEVE ficar em arquivo versionado (`prompts/*.md`),
nunca como string dentro do Python (RNF-M4). Adicionar uma etapa nova DEVE
exigir somente um prompt e uma linha na tabela de etapas, sem alterar o loop
principal; adicionar um MCP novo DEVE exigir somente configuração (RNF-M5,
RF-16). Toda mudança de comportamento DEVE passar por commit.

### X. Portabilidade e Reprodutibilidade

`uv sync` DEVE instalar a versão exata do Python e das dependências do
`uv.lock`; o programa roda com `uv run notion-copilot` em macOS e Linux
(RNF-P1/P2). Credenciais SOMENTE no `.env` (permissão 600, `.gitignore`,
`.env.example` sem valores) — nenhum segredo no repositório (RNF-S6).
Degradação graciosa é preferível a falha total (RNF-P4).

## Red Flags de Design (Ousterhout, *A Philosophy of Software Design*, 2019)

Estes 14 red flags são regras constitucionais (RNF-M6): código que incorrer
em qualquer um deles NÃO DEVE ser mergeado. A v2 não repete nenhum problema
do catálogo "Red flags — análise de 03/10/2026".

1. **Shallow Module** — É proibido módulo cuja interface é complicada em
   relação à funcionalidade que presta. Módulo pequeno e raso não ajuda
   contra a complexidade: o custo de aprender a interface anula o benefício
   de não conhecer o interior.
2. **Information Leakage** — O mesmo conhecimento NÃO DEVE aparecer em dois
   lugares (ex.: dois módulos que entendem o formato de um block do Notion).
3. **Temporal Decomposition** — A estrutura do código NÃO DEVE espelhar a
   ordem de execução. Se o mesmo conhecimento é usado em momentos diferentes
   (refinar → planejar → executar), ele pertence a um único módulo, não a um
   por fase. *Nota: a tabela de etapas centraliza esse conhecimento
   (`domain/stages.py`).*
4. **Overexposure** — A API de um recurso usado com frequência NÃO DEVE
   forçar o consumidor a aprender recursos raros.
5. **Pass-Through Method** — Método que só repassa argumentos a outro método
   é proibido: indica divisão de responsabilidade mal feita entre as classes.
6. **Repetition** — Código repetido (ou quase) é red flag de abstração
   errada ou inexistente. Fatorar no lugar certo, não copiar.
7. **Special-General Mixture** — Mecanismo genérico NÃO DEVE conter código
   especializado para um caso particular de uso.
8. **Conjoined Methods** — Deve ser possível entender cada método
   independentemente. Dois pedaços de código que só se entendem olhando um
   para o outro são red flag.
9. **Comment Repeats Code** — Comentário que repete o óbvio do código ao
   lado não ajuda e será removido. Comentário documenta o que não está
   visível no código.
10. **Implementation Documentation Contaminates Interface** — Docstring de
    interface NÃO DEVE descrever detalhes de implementação desnecessários
    para usar o módulo.
11. **Vague Name** — Nome largo o bastante para se referir a muitas coisas
    não informa nada. Nomes vagos (`data`, `manager`, `util`) são red flag.
12. **Hard to Pick Name** — Se é difícil achar um nome simples e claro, o
    objeto por baixo provavelmente tem design confuso. Renomear não basta;
    repensar o design.
13. **Hard to Describe** — Se não cabe num comentário simples e completo a
    descrição de um método ou variável, o design dela merece revisão.
14. **Nonobvious Code** — Código cujo significado e comportamento não se
    entendem numa leitura rápida é red flag.

## Segurança e Governança do Agente

- **Princípio da menor ferramenta:** cada etapa recebe só os MCPs de que
  precisa (RF-15); token do Notion do agente é somente leitura e restrito
  às páginas liberadas (RNF-S1).
- **Sem operações destrutivas:** o orquestrador não implementa ação de
  apagar nem arquivar; logo, nenhuma configuração pode expor essa
  capacidade (RNF-S2, Non-Goal 1).
- **Conteúdo externo é informação, nunca ordem:** o prompt instrui o agente
  a tratar texto de sites e páginas como dado. Se desobedecer, S1 e S2
  limitam o dano (RNF-S4).
- **Segredos:** somente `.env` permissão 600; API key do modelo passada só
  ao subprocesso `claude`, nunca como variável global (RNF-S6).
- **Confiabilidade:** idempotência por card (RNF-C1), sem rodadas
  sobrepostas (RNF-C2), erro isolado por card (RNF-C3), timeout de 10 min
  por execução (RNF-C4), retry com backoff limitado (RNF-C5), card
  abandonado vira ⚠️ (RNF-C6).

## Workflow de Desenvolvimento e Qualidade (Python)

- **Ferramentas obrigatórias:** `uv` para ambiente e dependências
  (`uv.lock` é a verdade), `ruff` para lint e formatação, `mypy` para tipos,
  `pytest` para testes. Type hints em todo código novo de `domain/` e
  `application/`.
- **Validação de dados na fronteira:** `.env` e ações JSON propostas pelo
  agente são validados com Pydantic — nada entra no núcleo sem validação.
- **Erros:** exceções específicas por camada; adapter traduz erros externos
  (Notion, CLI) para tipos do domínio. Falha tem estado visível no board
  (⚠️/❓) e comentário com `run_id` (RF-13/14, RNF-O4).
- **Estrutura de pastas** segue o design doc (seção 4): cada pasta
  corresponde a uma camada documentada (RNF-M2). Alguém que nunca viu o
  código DEVE descobrir onde mudar algo lendo só as seções 4 e 5.
- **Spec Kit:** features passam por `specify → plan → tasks → implement`;
  decisões de arquitetura viram ADR; a constituição se sobrepõe a qualquer
  prática que a contradiga.
- **Documentação como critério de pronto:** o projeto é portfólio — a autora
  DEVE conseguir explicar cada peça para outra pessoa. README permite
  instalar sem ajuda em menos de 5 minutos (RF-17).

## Governance

- Esta constituição se sobrepõe a qualquer prática, prompt ou decisão de
  implementação que a contradiga. Em conflito, ganha a constituição.
- Princípios I (regras em código), III (segurança por ausência de
  ferramenta) e V (aprovação humana) são NON-NEGOTIABLE: nenhuma emenda por
  implementação pode violá-los; mudá-los exige nova ratificação.
- Emendas exigem: motivação escrita, versão incrementada por semver
  (MAJOR: remoção/redefinição incompatível; MINOR: novo princípio ou seção;
  PATCH: esclarecimento), e plano de migração quando afetar código existente.
- Toda revisão de código/PR DEVE verificar conformidade com os 14 red flags
  e com os RNFs citados; complexidade acidental deve ser justificada.
- Decisões de arquitetura novas viram ADR em `docs/notion-copilot-adrs.md`;
  ADRs aceitos são imutáveis e substituídos por novos ADRs.
- Para orientação de desenvolvimento do dia a dia, consultar os ADRs e o
  design doc antes de propor mudanças estruturais.

**Version**: 1.0.1 | **Ratified**: 2026-10-10 | **Last Amended**: 2026-10-10
