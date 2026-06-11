---
tags:
  - blueprint
  - surrogate
  - SWAN
  - GA
  - obsidian
aliases:
  - Blueprints Delivery Plan
  - Plano de Entregas dos Blueprints
created: 2026-05-16
status: ativo
---

# BLUEPRINTS_DELIVERY_PLAN

> Mapa oficial da fase de blueprints para o surrogate do SNL-SWAN no loop do GA.

## Objetivo

Este documento define a sequência oficial de entregas da camada de blueprints que liga o plano auditado à implementação futura. O objetivo é evitar confusão, lacunas de especificação e decisões improvisadas durante a escrita dos ficheiros finais.

O foco é produzir especificações ficheiro a ficheiro, suficientemente detalhadas para permitir implementação posterior sem reabrir decisões fundamentais já fechadas no plano auditado.

## O que é um blueprint executável

Neste projeto, um blueprint executável não é ainda código de produção. Também não é apenas uma lista de ficheiros.

É uma especificação operacional de cada ficheiro alvo, com detalhe suficiente para definir:
- objetivo do ficheiro
- lugar no pipeline
- inputs
- outputs
- funções ou classes obrigatórias
- fluxo interno
- validações obrigatórias
- erros e logs
- diferenças entre modo B e modo C
- critérios de aceite
- riscos e armadilhas

## Princípios da fase

1. Primeiro fecha-se o contrato, depois escreve-se o código.
2. Tudo o que for comum a B e C deve ser especificado uma vez só.
3. Tudo o que divergir entre B e C deve aparecer explicitamente como bifurcação controlada.
4. O modo B é a baseline operacional.
5. O modo C é uma trilha separada, mais pesada, mas suportada desde já no desenho.
6. O código de restrições geométricas do GA continua a ser a fonte de verdade para viabilidade de layout.
7. A ordenação canónica dos WECs é obrigatória em todos os pontos do pipeline.
8. O armazenamento de `.mat` deve ser tratado como ativo do projeto, não como detalhe descartável.

## Estratégia de entrega

A produção dos blueprints será feita em blocos curtos, mas completos. Cada entrega fecha um subconjunto lógico do sistema e prepara a entrega seguinte.

Isto evita abrir demasiadas frentes ao mesmo tempo e reduz o risco de inconsistência entre documentos.

## Sequência oficial de entregas

### Entrega E1

**Ficheiro:** `BLUEPRINTS_DELIVERY_PLAN.md`

**Função:** servir como mapa-mãe da fase de blueprints.

**Conteúdo mínimo:**
- definição do que é blueprint executável
- lista das entregas
- ordem de produção
- regra de separação entre núcleo comum, modo B e modo C
- critérios de conclusão da fase

**Estado:** esta entrega.

### Entrega E2

**Ficheiro:** `BLUEPRINTS_INDEX.md`

**Função:** índice mestre dos blueprints.

**Conteúdo mínimo:**
- lista de todos os blueprints previstos
- dependências entre ficheiros
- marcação do que é comum a B e C
- marcação do que é exclusivo de B
- marcação do que é exclusivo de C
- ordem recomendada de leitura e implementação

**Objetivo de controlo:** impedir perda de rastreabilidade ao longo da sequência.

### Entrega E3

**Ficheiro:** `BLUEPRINT_CONFIG_GLOBAL.md`

**Função:** fechar contratos globais e schemas base.

**Conteúdo mínimo:**
- contrato de `config/paths.yaml`
- contrato de `config/problem.yaml`
- convenção de ordenação canónica
- schema de `case_id`
- schema dos metadados por caso
- schema do dataset congelado
- contrato formal do modo B
- contrato formal do modo C
- regras de compatibilidade de dados históricos

**Objetivo de controlo:** impedir que cada script invente o seu próprio formato.

### Entrega E4

**Ficheiro:** `BLUEPRINT_01_GENERATE_LAYOUTS.md`

**Função:** especificar a geração de layouts e amostragem de estados de mar.

**Conteúdo mínimo:**
- geração de candidatos
- uso do filtro geométrico
- ordenação canónica
- deduplicação de layouts
- mistura entre layouts aleatórios e famílias geométricas forçadas
- amostragem dos estados de mar com base na scatter diagram

### Entrega E5

**Ficheiro:** `BLUEPRINT_02_BUILD_SWAN_INPUTS.md`

**Função:** especificar a construção dos casos do SNL-SWAN.

**Conteúdo mínimo:**
- estrutura das pastas por caso
- ficheiros copiados e ficheiros gerados
- escrita do `.swn`
- naming convention
- metadados mínimos do caso

### Entrega E6

**Ficheiro:** `BLUEPRINT_03_RUN_SWAN_BATCH.md`

**Função:** especificar a execução batch idempotente.

**Conteúdo mínimo:**
- fila de execução
- retoma automática
- timeout
- paralelização
- logs
- status por caso
- tripwires de execução

### Entrega E7

**Ficheiro:** `BLUEPRINT_04_PARSE_OUTPUTS.md`

**Função:** especificar parsing, sanity checks e extração dos outputs.

**Conteúdo mínimo:**
- leitura de `P_total`
- leitura do `.mat`
- limpeza de secos
- cálculo de HRA para modo B
- indexação do campo para modo C
- sanity checks físicos
- critérios para rejeitar um caso

### Entrega E8

**Ficheiro:** `BLUEPRINT_05_BUILD_DATASET.md`

**Função:** especificar a montagem e congelamento do dataset.

**Conteúdo mínimo:**
- fusão dos inputs e outputs
- separação entre dataset B e dataset C
- validação de casos históricos
- ficheiros finais de dataset
- relatórios estatísticos do dataset

### Entrega E9

**Ficheiro:** `BLUEPRINT_06_TRAIN_MODEL.md`

**Função:** especificar o treino do surrogate.

**Conteúdo mínimo:**
- split treino/validação/teste
- baseline XGBoost para modo B
- trilha de treino para modo C
- normalização
- outputs dos artefactos de treino
- critérios de bloqueio

### Entrega E10

**Ficheiro:** `BLUEPRINT_07_VALIDATE_MODEL.md`

**Função:** especificar a validação rigorosa.

**Conteúdo mínimo:**
- validação estática
- validação local
- validação dinâmica
- monitorização do top 10 por cento
- critérios de aprovação

### Entrega E11

**Ficheiro:** `BLUEPRINT_08_EXPORT_SURROGATE.md`

**Função:** especificar a exportação do modelo e do contrato de inferência.

**Conteúdo mínimo:**
- objecto exportado
- scalers
- parâmetros min-max
- validações de input
- safety checks de output
- diferenças entre exportação B e C

### Entrega E12

**Ficheiro:** `BLUEPRINT_09_USE_IN_GA.md`

**Função:** especificar a integração do surrogate no GA.

**Conteúdo mínimo:**
- assinatura da função de avaliação
- predição vectorizada
- ligação com os pesos do fitness
- pontos de verificação com SWAN real
- logs operacionais

### Entrega E13

**Ficheiro:** `BLUEPRINT_TRACEABILITY.md`

**Função:** matriz de rastreabilidade.

**Conteúdo mínimo:**
- requisito do plano auditado
- ficheiro de blueprint onde foi especificado
- modo B ou C afetado
- dependências
- estado de cobertura

### Entrega E14

**Ficheiro:** `BLUEPRINT_REVIEW_FINAL.md`

**Função:** revisão final da camada de blueprints.

**Conteúdo mínimo:**
- contradições encontradas
- lacunas restantes
- duplicações
- decisões ainda em aberto
- checklist para passagem à implementação

## Ordem oficial de produção

| Ordem | Entrega | Ficheiro |
|---|---|---|
| 1 | E1 | `BLUEPRINTS_DELIVERY_PLAN.md` |
| 2 | E2 | `BLUEPRINTS_INDEX.md` |
| 3 | E3 | `BLUEPRINT_CONFIG_GLOBAL.md` |
| 4 | E4 | `BLUEPRINT_01_GENERATE_LAYOUTS.md` |
| 5 | E5 | `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` |
| 6 | E6 | `BLUEPRINT_03_RUN_SWAN_BATCH.md` |
| 7 | E7 | `BLUEPRINT_04_PARSE_OUTPUTS.md` |
| 8 | E8 | `BLUEPRINT_05_BUILD_DATASET.md` |
| 9 | E9 | `BLUEPRINT_06_TRAIN_MODEL.md` |
| 10 | E10 | `BLUEPRINT_07_VALIDATE_MODEL.md` |
| 11 | E11 | `BLUEPRINT_08_EXPORT_SURROGATE.md` |
| 12 | E12 | `BLUEPRINT_09_USE_IN_GA.md` |
| 13 | E13 | `BLUEPRINT_TRACEABILITY.md` |
| 14 | E14 | `BLUEPRINT_REVIEW_FINAL.md` |

## Dependências críticas

A fase tem quatro dependências mestras.

1. `BLUEPRINTS_INDEX.md` depende deste ficheiro.
2. `BLUEPRINT_CONFIG_GLOBAL.md` depende do índice.
3. Todos os blueprints de scripts dependem do documento de configuração global.
4. A rastreabilidade e a revisão final dependem da conclusão dos blueprints anteriores.

Sem fechar E3, não se deve produzir E4 a E12 como versão final.

## Regra de escrita dos blueprints

Cada blueprint futuro deve seguir esta estrutura fixa:

1. objetivo do ficheiro
2. lugar no pipeline
3. inputs esperados
4. outputs produzidos
5. funções e classes obrigatórias
6. fluxo interno
7. validações obrigatórias
8. erros e logs
9. diferenças entre B e C
10. dependências
11. critérios de aceite
12. riscos e armadilhas

## Critérios de conclusão da fase de blueprints

A fase de blueprints só termina quando todos os pontos abaixo estiverem satisfeitos:

- todos os ficheiros E1 a E14 existirem
- cada blueprint estiver alinhado com o plano auditado
- a separação entre núcleo comum, B e C estiver explícita em todos os ficheiros relevantes
- não existirem decisões fundamentais abertas dentro dos blueprints
- a matriz de rastreabilidade mostrar cobertura total dos requisitos do plano
- a revisão final não encontrar contradições bloqueantes

## Regras para não perder o controlo

- não saltar E3
- não escrever blueprint de código antes de fechar contratos globais
- não misturar decisão de output B com C dentro do mesmo bloco sem sinalização clara
- não criar ficheiro novo fora do índice mestre sem o registar
- não usar o blueprint para discutir ideias vagas; cada documento tem de fechar contratos operacionais

## Resultado esperado ao fim da fase

No final desta fase, deve existir uma camada documental suficientemente precisa para começar a implementação sem improvisar a estrutura dos ficheiros, os formatos dos dados, os contratos de interface e os critérios de validação.

Isso não significa que o código estará pronto. Significa que o sistema já estará desenhado ao ponto de a implementação virar execução disciplinada, e não exploração solta.

## Ligações

- [[surrogate_swan_plano_v2_auditado]]
- [[BLUEPRINTS_INDEX]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[BLUEPRINT_TRACEABILITY]]
- [[BLUEPRINT_REVIEW_FINAL]]
