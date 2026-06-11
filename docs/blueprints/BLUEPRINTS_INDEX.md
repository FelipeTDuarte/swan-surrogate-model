---
tags:
  - blueprint
  - surrogate
  - SWAN
  - GA
  - obsidian
aliases:
  - Entrega 1 dos Blueprints
  - Blueprints Index
created: 2026-05-16
status: entrega-1
---

# BLUEPRINTS_INDEX

> Índice mestre da fase de blueprints do surrogate SNL-SWAN para uso no loop do GA.

## Função deste documento

Este ficheiro é o índice central de toda a camada de blueprints. A sua função é manter rastreabilidade, ordem de leitura, ordem de produção e visão clara das dependências entre os documentos.

Ele existe para evitar três problemas comuns:
- perder o controlo da sequência de entregas
- criar ficheiros fora de ordem lógica
- misturar partes comuns com decisões específicas dos modos B e C

## Relação com o plano auditado

Este índice não substitui o plano auditado. Ele serve como mapa operacional da fase seguinte.

A hierarquia correta passa a ser:
1. [[surrogate_swan_plano_v2_auditado]]
2. [[BLUEPRINTS_DELIVERY_PLAN]]
3. `BLUEPRINTS_INDEX.md`
4. blueprints ficheiro a ficheiro
5. implementação posterior

## Modos suportados

Este conjunto de blueprints suporta dois modos de output do surrogate.

### Modo B

O surrogate prevê:
- `P_total`
- um vetor curto de HRA para áreas fixas e explícitas

Este é o modo operacional base.

### Modo C

O surrogate prevê:
- `P_total`
- o campo completo de `Hs` no domínio de referência

Este é o modo mais flexível e mais pesado.

## Convenção de leitura dos blueprints

Cada blueprint futuro deve deixar explícito o que pertence a:
- **núcleo comum**
- **ramo B**
- **ramo C**
- **impacto nos ficheiros seguintes**

Isto impede que B e C sejam tratados como dois projetos independentes e também impede que fiquem misturados sem controlo.

## Mapa completo dos blueprints

| Código | Ficheiro | Tipo | Comum / B / C | Estado |
|---|---|---|---|---|
| E1 | `BLUEPRINTS_DELIVERY_PLAN.md` | mapa da fase | comum | concluído |
| E2 | `BLUEPRINTS_INDEX.md` | índice mestre | comum | concluído |
| E3 | `BLUEPRINT_CONFIG_GLOBAL.md` | contratos globais | comum + B + C | por fazer |
| E4 | `BLUEPRINT_01_GENERATE_LAYOUTS.md` | pipeline de dados | comum | por fazer |
| E5 | `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` | pipeline de dados | comum | por fazer |
| E6 | `BLUEPRINT_03_RUN_SWAN_BATCH.md` | pipeline de dados | comum | por fazer |
| E7 | `BLUEPRINT_04_PARSE_OUTPUTS.md` | parsing e targets | comum + B + C | por fazer |
| E8 | `BLUEPRINT_05_BUILD_DATASET.md` | dataset final | comum + B + C | por fazer |
| E9 | `BLUEPRINT_06_TRAIN_MODEL.md` | treino | comum + B + C | por fazer |
| E10 | `BLUEPRINT_07_VALIDATE_MODEL.md` | validação | comum + B + C | por fazer |
| E11 | `BLUEPRINT_08_EXPORT_SURROGATE.md` | exportação | comum + B + C | por fazer |
| E12 | `BLUEPRINT_09_USE_IN_GA.md` | integração no GA | comum + B + C | por fazer |
| E13 | `BLUEPRINT_TRACEABILITY.md` | rastreabilidade | comum | por fazer |
| E14 | `BLUEPRINT_REVIEW_FINAL.md` | revisão final | comum | por fazer |

## Ordem oficial de produção

| Ordem | Entrega | Ficheiro | Dependência imediata |
|---|---|---|---|
| 1 | E1 | `BLUEPRINTS_DELIVERY_PLAN.md` | plano auditado |
| 2 | E2 | `BLUEPRINTS_INDEX.md` | E1 |
| 3 | E3 | `BLUEPRINT_CONFIG_GLOBAL.md` | E2 |
| 4 | E4 | `BLUEPRINT_01_GENERATE_LAYOUTS.md` | E3 |
| 5 | E5 | `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` | E3 |
| 6 | E6 | `BLUEPRINT_03_RUN_SWAN_BATCH.md` | E3 + E5 |
| 7 | E7 | `BLUEPRINT_04_PARSE_OUTPUTS.md` | E3 + E6 |
| 8 | E8 | `BLUEPRINT_05_BUILD_DATASET.md` | E3 + E7 |
| 9 | E9 | `BLUEPRINT_06_TRAIN_MODEL.md` | E3 + E8 |
| 10 | E10 | `BLUEPRINT_07_VALIDATE_MODEL.md` | E3 + E8 + E9 |
| 11 | E11 | `BLUEPRINT_08_EXPORT_SURROGATE.md` | E3 + E9 + E10 |
| 12 | E12 | `BLUEPRINT_09_USE_IN_GA.md` | E3 + E11 |
| 13 | E13 | `BLUEPRINT_TRACEABILITY.md` | E3 a E12 |
| 14 | E14 | `BLUEPRINT_REVIEW_FINAL.md` | E3 a E13 |

## Dependências críticas

### Dependência D1

`BLUEPRINT_CONFIG_GLOBAL.md` é o documento que fecha os contratos que todos os outros usam. Sem ele, os blueprints seguintes ainda seriam provisórios.

### Dependência D2

Os ficheiros `04_parse_outputs`, `05_build_dataset`, `06_train_model`, `07_validate_model`, `08_export_surrogate` e `09_use_in_ga` dependem diretamente da definição formal dos modos B e C.

### Dependência D3

A rastreabilidade e a revisão final só fazem sentido depois de todos os blueprints operacionais existirem.

## Classificação por blocos

### Bloco A — Governação da fase

| Ficheiro | Papel |
|---|---|
| `BLUEPRINTS_DELIVERY_PLAN.md` | mapa da fase |
| `BLUEPRINTS_INDEX.md` | índice mestre |
| `BLUEPRINT_TRACEABILITY.md` | controlo de cobertura |
| `BLUEPRINT_REVIEW_FINAL.md` | auditoria final |

### Bloco B — Contratos globais

| Ficheiro | Papel |
|---|---|
| `BLUEPRINT_CONFIG_GLOBAL.md` | schemas, convenções, contratos B/C, metadados |

### Bloco C — Pipeline de dados

| Ficheiro | Papel |
|---|---|
| `BLUEPRINT_01_GENERATE_LAYOUTS.md` | geração de layouts válidos |
| `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` | construção dos casos do SWAN |
| `BLUEPRINT_03_RUN_SWAN_BATCH.md` | execução batch |
| `BLUEPRINT_04_PARSE_OUTPUTS.md` | parsing de outputs |
| `BLUEPRINT_05_BUILD_DATASET.md` | montagem do dataset congelado |

### Bloco D — ML e validação

| Ficheiro | Papel |
|---|---|
| `BLUEPRINT_06_TRAIN_MODEL.md` | treino do surrogate |
| `BLUEPRINT_07_VALIDATE_MODEL.md` | validação estática, local e dinâmica |

### Bloco E — Operação

| Ficheiro | Papel |
|---|---|
| `BLUEPRINT_08_EXPORT_SURROGATE.md` | exportação do modelo |
| `BLUEPRINT_09_USE_IN_GA.md` | integração com o GA |

## Quais blueprints divergem entre B e C

| Ficheiro | Divergência B/C | Grau |
|---|---|---|
| `BLUEPRINT_CONFIG_GLOBAL.md` | contrato de output e schema | alta |
| `BLUEPRINT_04_PARSE_OUTPUTS.md` | HRA vetorial vs campo completo | alta |
| `BLUEPRINT_05_BUILD_DATASET.md` | dataset escalar vs dataset indexado por `.mat` | alta |
| `BLUEPRINT_06_TRAIN_MODEL.md` | regressão tabular vs previsão de campo | muito alta |
| `BLUEPRINT_07_VALIDATE_MODEL.md` | métricas e validação espacial | alta |
| `BLUEPRINT_08_EXPORT_SURROGATE.md` | interface e artefactos | média |
| `BLUEPRINT_09_USE_IN_GA.md` | consumo do output | média |

Os restantes são maioritariamente comuns.

## Regras de produção das próximas entregas

Cada entrega futura deve cumprir estas regras.

### Regra 1

Não reabrir decisões já fechadas no plano auditado, exceto se aparecer contradição real.

### Regra 2

Sempre que um ficheiro afetar B e C de maneira diferente, isso deve aparecer em secções separadas.

### Regra 3

Sempre que um ficheiro depender de schema, esse schema deve ser referenciado a partir de `BLUEPRINT_CONFIG_GLOBAL.md`.

### Regra 4

Nenhum blueprint pode assumir que “isso se decide depois” para algo que bloqueie implementação.

### Regra 5

Sempre que existir risco de erro silencioso, o blueprint deve incluir:
- validação obrigatória
- condição de falha
- log correspondente

## Critérios de qualidade do índice

Este índice só é considerado válido se:
- listar todos os blueprints previstos
- mostrar a ordem oficial de produção
- mostrar as dependências críticas
- identificar claramente os pontos de bifurcação entre B e C
- permitir ao leitor saber o próximo ficheiro a produzir sem ambiguidade

## Próxima entrega

A próxima entrega, pela ordem oficial, é:

**Entrega 2**  
`BLUEPRINT_CONFIG_GLOBAL.md`

Esse documento é o mais importante da fase porque fecha os contratos globais que todos os outros blueprints vão usar.

## Estado atual da fase

| Entrega | Estado |
|---|---|
| E1 | concluída |
| E2 | concluída |
| E3 | pendente |
| E4 | pendente |
| E5 | pendente |
| E6 | pendente |
| E7 | pendente |
| E8 | pendente |
| E9 | pendente |
| E10 | pendente |
| E11 | pendente |
| E12 | pendente |
| E13 | pendente |
| E14 | pendente |

## Ligações

- [[BLUEPRINTS_DELIVERY_PLAN]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[BLUEPRINT_TRACEABILITY]]
- [[BLUEPRINT_REVIEW_FINAL]]
- [[surrogate_swan_plano_v2_auditado]]
