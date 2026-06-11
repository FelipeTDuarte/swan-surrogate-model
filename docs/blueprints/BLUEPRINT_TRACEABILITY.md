---
tags:
  - blueprint
  - traceability
  - surrogate
  - SWAN
  - GA
aliases:
  - Entrega 12 dos Blueprints
  - Blueprint Traceability
created: 2026-05-16
status: entrega-12
---

# BLUEPRINT_TRACEABILITY

> Matriz de rastreabilidade entre o plano auditado e os blueprints já produzidos, para provar cobertura, localizar decisões e evitar perda silenciosa de requisitos.

## Função deste documento

Este ficheiro liga cada requisito relevante do plano auditado aos blueprints onde esse requisito foi especificado operacionalmente.

O objetivo é impedir duas falhas clássicas: achar que algo “está implícito” quando não está escrito em lado nenhum, e perder decisões importantes no meio da sequência de entregas.

## Estado da cobertura

### Verificações estruturais

- plano auditado disponível: YES
- índice mestre disponível: YES
- blueprints operacionais principais disponíveis: YES
- contrato B/C explícito: YES
- fonte de verdade geométrica preservada: YES
- validação do top 10 por cento preservada: YES
- dataset congelado preservado: YES
- bounds de normalização preservados na exportação: YES

## Como ler esta matriz

Cada linha abaixo liga:
- requisito ou decisão do plano
- ficheiro(s) onde isso foi especificado
- modo afetado
- estado de cobertura
- observação curta

## Matriz principal

| ID | Requisito / decisão | Blueprint(s) | Modo | Cobertura | Observação |
|---|---|---|---|---|---|
| R01 | `n_wecs` fixo por surrogate | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | contrato global e verificação na integração |
| R02 | geometria válida é inegociável | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_01_GENERATE_LAYOUTS.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | fonte de verdade mantida no GA |
| R03 | ordenação canónica obrigatória | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_01_GENERATE_LAYOUTS.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | aplicada no dataset e na inferência |
| R04 | estados de mar no contrato `[Hs,Tp,Dir]` | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_01_GENERATE_LAYOUTS.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | ordem e unidades fixadas |
| R05 | importance sampling a partir da scatter diagram | `BLUEPRINT_01_GENERATE_LAYOUTS.md` | B+C | completa | cobertura operacional explícita |
| R06 | famílias geométricas forçadas no dataset | `BLUEPRINT_01_GENERATE_LAYOUTS.md` | B+C | completa | reduz risco de cobertura pobre |
| R07 | construção de casos por `case_id` e diretório próprio | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` | B+C | completa | naming e estrutura de run definidos |
| R08 | execução batch idempotente | `BLUEPRINT_03_RUN_SWAN_BATCH.md` | B+C | completa | retoma e estados explícitos |
| R09 | parsing com sanity checks físicos | `BLUEPRINT_04_PARSE_OUTPUTS.md` | B+C | completa | filtros antes do dataset |
| R10 | tratamento de secos e valores inválidos no campo | `BLUEPRINT_04_PARSE_OUTPUTS.md` | B+C | completa | política de limpeza explícita |
| R11 | distinção formal entre modo B e modo C | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_04_PARSE_OUTPUTS.md`, `BLUEPRINT_05_BUILD_DATASET.md`, `BLUEPRINT_06_TRAIN_MODEL.md` | B+C | completa | contratos separados e consistentes |
| R12 | casos históricos válidos precisam de contrato mínimo | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_05_BUILD_DATASET.md` | B+C | completa | compatibilidade de dados históricos fixada |
| R13 | guardar `.mat` como ativo do projeto | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_04_PARSE_OUTPUTS.md`, `BLUEPRINT_05_BUILD_DATASET.md` | B+C | completa | reutilização futura preservada |
| R14 | dataset congelado e versionado | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_05_BUILD_DATASET.md` | B+C | completa | treino proibido de refazer merge ad hoc |
| R15 | baseline operacional do modo B com XGBoost | `BLUEPRINT_06_TRAIN_MODEL.md` | B | completa | MLP fica como alternativa |
| R16 | modo C é trilha separada de previsão de campo | `BLUEPRINT_06_TRAIN_MODEL.md` | C | completa | não tratado como extensão trivial |
| R17 | métricas de ranking e top 10 por cento | `BLUEPRINT_06_TRAIN_MODEL.md`, `BLUEPRINT_07_VALIDATE_MODEL.md` | B+C | completa | foco na região relevante do GA |
| R18 | validação local por perturbação de layouts | `BLUEPRINT_07_VALIDATE_MODEL.md` | B+C | completa | estabilidade local exigida |
| R19 | validação dinâmica com SWAN real | `BLUEPRINT_07_VALIDATE_MODEL.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | rechecagem operacional prevista |
| R20 | exportar só modelos aprovados | `BLUEPRINT_08_EXPORT_SURROGATE.md` | B+C | completa | decisão de validação bloqueia exportação |
| R21 | bundle exportado deve incluir bounds, scaler e features | `BLUEPRINT_08_EXPORT_SURROGATE.md` | B+C | completa | contexto mínimo preservado |
| R22 | normalização min-max `[0.01,1]` dentro da fitness | `BLUEPRINT_CONFIG_GLOBAL.md`, `BLUEPRINT_06_TRAIN_MODEL.md`, `BLUEPRINT_08_EXPORT_SURROGATE.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | bounds congelados, sem min-max dinâmico |
| R23 | layout inválido não entra na seleção por penalização tardia | `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | exclusão antes da inferência |
| R24 | rechecagem periódica durante operação | `BLUEPRINT_07_VALIDATE_MODEL.md`, `BLUEPRINT_09_USE_IN_GA.md` | B+C | completa | mecanismo de controlo contínuo |

## Mapa por ficheiro

### `BLUEPRINT_CONFIG_GLOBAL.md`

Cobre contratos globais, `paths.yaml`, `problem.yaml`, `case_id`, layout, estados de mar, modo B, modo C, compatibilidade histórica, bounds da fitness e regras de versionamento.

### `BLUEPRINT_01_GENERATE_LAYOUTS.md`

Cobre geração de layouts válidos, famílias geométricas, deduplicação, ordenação canónica, sampling da scatter diagram e geração de candidatos.

### `BLUEPRINT_02_BUILD_SWAN_INPUTS.md`

Cobre montagem dos diretórios por caso, renderização do `INPUT.swn`, assets estáticos, manifesto do caso e índice de runs preparados.

### `BLUEPRINT_03_RUN_SWAN_BATCH.md`

Cobre execução batch, estratégias de lançamento, timeout, retoma, estados de execução, logs e outputs mínimos.

### `BLUEPRINT_04_PARSE_OUTPUTS.md`

Cobre extração de `P_total`, leitura e limpeza do campo de `Hs`, cálculo do HRA, classificação B/C, sanity checks físicos e falhas de `.mat`.

### `BLUEPRINT_05_BUILD_DATASET.md`

Cobre merges finais, inclusão e exclusão por modo, congelamento e versionamento dos datasets, registry, estatísticas e exclusions report.

### `BLUEPRINT_06_TRAIN_MODEL.md`

Cobre split reproduzível, scalers, baseline B, trilha C, métricas de treino, bundles e registry do treino.

### `BLUEPRINT_07_VALIDATE_MODEL.md`

Cobre validação estática, top 10 por cento, sensibilidade local, validação dinâmica, decisão de aprovação e restrições.

### `BLUEPRINT_08_EXPORT_SURROGATE.md`

Cobre bundle exportado, manifesto de inferência, preservação de bounds, versionamento e bloqueio de exportação para modelos rejeitados.

### `BLUEPRINT_09_USE_IN_GA.md`

Cobre integração no GA, validação geométrica pré-inferência, ordenação canónica, normalização dentro da fitness, batch multiestado, auditoria e rechecagem periódica.

## Cobertura por modo

### Modo B

O modo B tem cobertura completa desde contrato, parsing, dataset, treino, validação, exportação e integração no GA.

### Modo C

O modo C também tem cobertura completa na camada de blueprints, mas com maior peso nos ficheiros de parsing, dataset, treino, validação e exportação por causa do target espacial.

## Itens intencionalmente fora de escopo desta fase

Os blueprints ainda não implementam código executável final. Eles fecham contratos e desenho operacional.

Também não fecham uma arquitetura única para o modelo de campo do modo C. Isso ficou deliberadamente aberto dentro de um contrato controlado, porque a representação do campo ainda pode ser decidida entre alternativas compatíveis com o plano.

## Lacunas atuais

No estado atual, não há lacunas bloqueantes óbvias entre o plano auditado e os blueprints operacionais já entregues.

A principal zona que ainda exigirá decisão de implementação, e não de especificação, é a escolha concreta da arquitetura e do formato interno do modelo do modo C.

## Regras para uso desta matriz

- sempre que um requisito do plano mudar, esta matriz deve ser atualizada
- sempre que surgir um novo blueprint, ele deve ser ligado aqui
- antes de passar para implementação, esta matriz deve ser relida em conjunto com `BLUEPRINT_REVIEW_FINAL.md`

## Critérios de aceite

Este documento só é considerado fechado se:
- permitir localizar cada decisão importante do plano em pelo menos um blueprint
- mostrar claramente a cobertura de B e C
- sinalizar lacunas reais em vez de criar falsa sensação de completude

## Ligações

- [[surrogate_swan_plano_v2_auditado]]
- [[BLUEPRINTS_INDEX]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[BLUEPRINT_REVIEW_FINAL]]
