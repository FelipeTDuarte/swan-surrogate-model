---
tags:
  - blueprint
  - data-pipeline
  - dataset
  - surrogate
  - SWAN
  - GA
aliases:
  - Entrega 7 dos Blueprints
  - Blueprint Build Dataset
created: 2026-05-16
status: entrega-7
---

# BLUEPRINT_05_BUILD_DATASET

> Especificação operacional do ficheiro responsável por consolidar os outputs parseados num dataset congelado, versionado e rastreável, separando corretamente os contratos do modo B e do modo C.

## Objetivo do ficheiro

Este ficheiro fecha a transição entre a fase de parsing e a fase de machine learning. O seu papel é reunir inputs, targets, metadados de compatibilidade e regras de inclusão para produzir datasets finais de treino, validação e teste em formato estável.

O objetivo não é voltar a interpretar outputs brutos do SWAN nem treinar modelos. O objetivo é decidir, de forma rastreável, que casos entram no dataset congelado, em que formato entram, e com que versão ficam registados.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_04_PARSE_OUTPUTS.md` produz tabelas parseadas e compatibilidade por caso
2. `BLUEPRINT_05_BUILD_DATASET.md` consolida e congela datasets B e C
3. `BLUEPRINT_06_TRAIN_MODEL.md` consome apenas os datasets congelados

Se este ficheiro falhar, o treino seguinte pode misturar casos inválidos, versões incompatíveis, contratos diferentes de output ou regras de inclusão não auditáveis.

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `hra.mode`
- `hra.areas`
- `training.split`
- `fitness.normalization`
- `fitness.p_total_bounds`
- `fitness.hra_bounds`

### Input 2 — `config/paths.yaml`

O ficheiro deve usar:
- `processed_dir`
- `reports_dir`
- `archive_dir`

### Input 3 — tabelas parseadas

O ficheiro deve consumir, no mínimo:
- `data/processed/parsed_cases.csv`
- `data/processed/parsed_targets_B.csv`
- `data/processed/parsed_targets_C.csv`

### Input 4 — candidatos ou banco de inputs

Para reconstruir os inputs finais do dataset, o ficheiro deve usar:
- `data/processed/candidates.csv`

Se o projeto decidir separar `layout_bank.csv` e `sea_state_bank.csv` como fontes auxiliares, isso pode ser usado, mas `candidates.csv` continua a ser a base principal do merge.

### Input 5 — manifestos e artefactos por caso

O ficheiro pode consultar `case_manifest.yaml` quando precisar de confirmar paths, grid, shape ou metadados de campo para o modo C.

## Outputs produzidos

### Output principal do modo B

Ficheiro sugerido:

```text
data/processed/dataset_B_v1.csv
```

Campos mínimos:

```text
case_id, x1, y1, ..., xN, yN, Hs, Tp, Dir, P_total, HRA_area_1, ..., HRA_area_k
```

### Output principal do modo C

Ficheiro sugerido:

```text
data/processed/dataset_C_index_v1.csv
```

Campos mínimos:

```text
case_id, x1, y1, ..., xN, yN, Hs, Tp, Dir, P_total, hs_field_file, grid_id, field_shape
```

### Outputs auxiliares obrigatórios

1. `data/processed/dataset_registry.yaml`
2. `reports/dataset_build_report.md`
3. `reports/dataset_statistics.yaml`
4. `reports/dataset_exclusions.csv`
5. `reports/logs/05_build_dataset.log`

## Função de cada output auxiliar

### `dataset_registry.yaml`

Guarda a identidade formal de cada dataset congelado, incluindo versão, data, problema, contrato e regras de inclusão.

### `dataset_build_report.md`

Resume o que entrou, o que ficou de fora, porquê, e que artefactos foram produzidos.

### `dataset_statistics.yaml`

Guarda estatísticas numéricas e distribuições relevantes do dataset.

### `dataset_exclusions.csv`

Regista todos os casos excluídos, com razão explícita.

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_parsed_tables()`

Carrega e valida `parsed_cases.csv`, `parsed_targets_B.csv` e `parsed_targets_C.csv`.

### 2. `load_candidates_table()`

Carrega `candidates.csv` e valida o schema dos inputs.

### 3. `merge_inputs_and_targets()`

Faz o merge entre inputs e targets com base em `case_id`.

### 4. `filter_valid_cases_for_mode(mode)`

Aplica as regras de inclusão para B ou C.

### 5. `build_dataset_B()`

Produz o dataset final do modo B.

### 6. `build_dataset_C()`

Produz o índice final do dataset do modo C.

### 7. `compute_dataset_statistics()`

Calcula estatísticas agregadas de inputs, outputs, cobertura e exclusões.

### 8. `write_dataset_registry()`

Regista a versão e o contrato do dataset produzido.

### 9. `write_exclusion_report()`

Guarda a lista de casos excluídos com motivo.

### 10. `freeze_dataset_artifacts()`

Persiste os ficheiros finais e garante que a versão fica imutável.

## Fluxo interno

### Etapa 1 — carregar configurações e tabelas base

Ler `problem.yaml`, `paths.yaml`, `candidates.csv` e as tabelas parseadas.

### Etapa 2 — validar integridade relacional

Confirmar que os `case_id` batem entre tabelas e que não há duplicações inesperadas.

### Etapa 3 — construir base consolidada

Juntar inputs tabulares e targets parseados numa tabela intermédia controlada.

### Etapa 4 — aplicar regras de inclusão por modo

Separar explicitamente os casos válidos para B e os válidos para C.

### Etapa 5 — produzir datasets finais

Escrever o dataset B e o índice do dataset C em ficheiros próprios, sem misturar contratos.

### Etapa 6 — calcular estatísticas e exclusões

Gerar relatórios numéricos, distribuições, contagens e razões de exclusão.

### Etapa 7 — congelar a versão

Guardar o registo formal do dataset e impedir que o treino seguinte dependa de reconstrução informal em memória.

## Regra central do ficheiro

O treino só pode consumir datasets congelados. Não é permitido que `06_train_model.py` refaça merges ad hoc com ficheiros parseados soltos.

Isto existe para evitar deriva silenciosa entre corridas de treino e para garantir que qualquer modelo pode ser traçado até a uma versão concreta de dataset.

## Regras de inclusão do modo B

Um caso entra no dataset B se, no mínimo:
- existir em `candidates.csv`
- existir em `parsed_targets_B.csv`
- `valid_for_B = true` em `parsed_cases.csv`
- tiver `P_total` finito
- tiver todas as colunas HRA requeridas preenchidas e finitas

### Exclusões típicas de B

- `P_total` em falta
- HRA em falta
- erro de merge por `case_id`
- falha de sanity check na fase anterior
- caso marcado como incompatível para B

## Regras de inclusão do modo C

Um caso entra no dataset C se, no mínimo:
- existir em `candidates.csv`
- existir em `parsed_targets_C.csv`
- `valid_for_C = true` em `parsed_cases.csv`
- tiver `P_total` finito
- tiver `hs_field_file` definido
- tiver `grid_id` e `field_shape` coerentes com o contrato do problema

### Exclusões típicas de C

- `.mat` ilegível
- shape incompatível
- campo incompleto
- grid inconsistente
- erro de merge por `case_id`
- caso marcado como incompatível para C

## Regra de compatibilidade B/C

Todo caso válido para C deve ser verificado quanto ao reaproveitamento para B. Se as áreas HRA estiverem disponíveis e os HRA tiverem sido calculados corretamente, esse caso deve aparecer também no dataset B.

O inverso não é obrigatório. Um caso pode ser válido para B e não para C.

## Contrato do dataset B

### Estrutura mínima

```text
case_id, x1, y1, ..., xN, yN, Hs, Tp, Dir, P_total, HRA_area_1, ..., HRA_area_k
```

### Regras

- o layout deve já estar em ordem canónica
- a ordem das colunas deve ser estável entre versões do mesmo contrato
- não incluir colunas derivadas temporárias que não façam parte do contrato do treino

### Observação

O dataset B é tabular e auto-suficiente para treino baseline com XGBoost ou MLP, sem precisar voltar ao diretório do caso.

## Contrato do dataset C

### Estrutura mínima

```text
case_id, x1, y1, ..., xN, yN, Hs, Tp, Dir, P_total, hs_field_file, grid_id, field_shape
```

### Regras

- o ficheiro de campo deve apontar para um artefacto congelado e estável
- `grid_id` deve identificar o grid de referência do campo
- `field_shape` deve ser compatível com o backend de treino previsto
- o índice C não substitui o artefacto do campo; ele referencia esse artefacto

### Observação

O dataset C é um dataset indexado, não um CSV gigante com o campo achatado dentro. O campo continua armazenado como artefacto externo controlado.

## Política de versionamento

### Regra principal

Sempre que mudares qualquer elemento que altere a composição ou o contrato do dataset, tens de gerar nova versão.

### Gatilhos mínimos de nova versão

- mudança nas áreas HRA
- mudança no envelope de estados de mar
- mudança na política de limpeza do campo
- mudança na regra de inclusão ou exclusão
- mudança nos bounds de normalização associados ao dataset
- incorporação de novos casos históricos
- mudança de `n_wecs`

### Convenção sugerida de naming

```text
dataset_B_v1.csv
dataset_C_index_v1.csv
```

Versões seguintes:

```text
dataset_B_v2.csv
dataset_C_index_v2.csv
```

## Contrato de `dataset_registry.yaml`

Este ficheiro deve guardar, no mínimo:

```yaml
dataset_version: "v1"
problem_id: "swan_surrogate_n28_v1"
n_wecs: 28
modes_built:
  B: true
  C: true
source_files:
  candidates: "data/processed/candidates.csv"
  parsed_cases: "data/processed/parsed_cases.csv"
  parsed_targets_B: "data/processed/parsed_targets_B.csv"
  parsed_targets_C: "data/processed/parsed_targets_C.csv"
inclusion_rules:
  require_valid_for_B: true
  require_valid_for_C: true
fitness_bounds:
  p_total_bounds: [0.0, 1.0]
  hra_bounds: [0.0, 1.0]
artifacts:
  dataset_B: "data/processed/dataset_B_v1.csv"
  dataset_C_index: "data/processed/dataset_C_index_v1.csv"
created_at: "..."
```

## Integridade relacional

### Validações obrigatórias

- `case_id` único em cada tabela base
- `case_id` presente em `candidates.csv` para todo caso incluído
- ausência de duplicações após merge
- coerência entre `n_wecs` e número de colunas do layout
- coerência entre número de áreas HRA e colunas HRA do modo B

### Regra de falha

Se um caso aparecer em `parsed_targets_B.csv` ou `parsed_targets_C.csv` mas não existir em `candidates.csv`, isso deve ser tratado como erro estrutural, não como detalhe menor.

## Estatísticas obrigatórias do dataset

O `dataset_statistics.yaml` deve conter, no mínimo:

```yaml
n_cases_total_candidates: 15000
n_cases_parsed: 13200
n_cases_dataset_B: 12000
n_cases_dataset_C: 9800
n_excluded_B: 1200
n_excluded_C: 3400
input_ranges:
  Hs: [0.5, 4.0]
  Tp: [5.0, 16.0]
  Dir: [220.0, 320.0]
output_ranges:
  P_total: [0.0, 999.0]
  HRA_area_1: [0.1, 3.2]
family_distribution:
  random_sparse: 2500
  grid_like: 2100
  row_aligned: 1800
  diagonal: 1600
  compact: 2000
  dispersed: 2000
```

### Estatísticas recomendadas adicionais

- percentagem de casos B reaproveitados de C
- distribuição de exclusões por motivo
- cobertura por faixas de `Hs`, `Tp` e `Dir`
- cobertura por família geométrica

## Relatório de exclusões

O ficheiro `dataset_exclusions.csv` deve conter, no mínimo:

```text
case_id, mode, exclusion_reason, source_table, details
```

### Regras

- um caso pode aparecer excluído de B e não de C, ou vice-versa
- a razão de exclusão deve ser explícita
- exclusões não devem ficar apenas no log textual

## Congelamento dos artefactos

### Regra

Depois de escrito, um dataset congelado não deve ser reeditado in place. Nova composição implica nova versão.

### Consequência prática

O treino tem de apontar para uma versão concreta, não para um ficheiro genérico que pode mudar debaixo dos pés.

## Split treino, validação e teste

### Responsabilidade deste ficheiro

Este blueprint não obriga a gerar já os splits finais, mas deixa aberta uma de duas políticas e exige que a escolhida fique registada no `dataset_registry.yaml`.

### Política A — split no treino

`06_train_model.py` recebe o dataset congelado inteiro e gera os splits de forma reproduzível a partir do `random_seed`.

### Política B — split já congelado aqui

Este ficheiro já gera, além do dataset principal, os ficheiros:
- `dataset_B_train_v1.csv`
- `dataset_B_val_v1.csv`
- `dataset_B_test_v1.csv`
- equivalentes para o índice C

### Recomendação atual

Para simplicidade inicial, usar a Política A, mas registar isso formalmente no registry.

## Logging

### Eventos mínimos a registar

- início da construção do dataset
- número de casos carregados por tabela
- número de casos aceites em B
- número de casos aceites em C
- número de exclusões por motivo
- versão gerada
- caminhos dos artefactos finais

## Núcleo comum, modo B e modo C

### Núcleo comum

Merge por `case_id`, validação relacional, versionamento, registry, estatísticas e exclusões pertencem ao núcleo comum.

### Diferença para B

No modo B, o resultado final é um dataset tabular pronto para treino supervisionado escalar ou multi-output curto.

### Diferença para C

No modo C, o resultado final é um índice tabular para campos externos congelados, com exigências adicionais de `grid_id` e `field_shape`.

### Regra prática

O pipeline deve gerar B e C em paralelo sempre que os artefactos existirem, em vez de obrigar o utilizador a reconstruir tudo duas vezes.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_04_PARSE_OUTPUTS.md`
- outputs parseados válidos do teu caso manual e do lote piloto

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- leia `candidates.csv` e tabelas parseadas
- faça merge relacional estável por `case_id`
- produza `dataset_B_vX.csv`
- produza `dataset_C_index_vX.csv`
- gere registry, estatísticas, exclusões e log
- impeça deriva silenciosa de versões

## Riscos e armadilhas

### Armadilha 1

Voltar a fazer merges informais dentro do treino. Isso destrói a função deste blueprint.

### Armadilha 2

Misturar contratos de B e C no mesmo ficheiro final. Isso dificulta treino, validação e exportação.

### Armadilha 3

Não versionar mudanças nas regras de inclusão. O dataset muda, mas o nome fica igual, e depois ninguém sabe explicar diferenças de desempenho.

### Armadilha 4

Guardar exclusões só em log textual. Isso torna auditoria posterior muito pior.

### Armadilha 5

Assumir que todo caso válido para B é automaticamente comparável em C. Não é.

## Checklist de implementação futura

- [ ] carregar `candidates.csv`
- [ ] carregar `parsed_cases.csv`
- [ ] carregar `parsed_targets_B.csv`
- [ ] carregar `parsed_targets_C.csv`
- [ ] validar unicidade de `case_id`
- [ ] fazer merge estável por `case_id`
- [ ] filtrar casos válidos para B
- [ ] filtrar casos válidos para C
- [ ] escrever `dataset_B_vX.csv`
- [ ] escrever `dataset_C_index_vX.csv`
- [ ] escrever `dataset_registry.yaml`
- [ ] escrever `dataset_statistics.yaml`
- [ ] escrever `dataset_exclusions.csv`
- [ ] escrever relatório de build
- [ ] guardar log agregado

## Ligações

- [[BLUEPRINT_04_PARSE_OUTPUTS]]
- [[BLUEPRINT_06_TRAIN_MODEL]]
- [[BLUEPRINT_07_VALIDATE_MODEL]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
