---
tags:
  - blueprint
  - training
  - machine-learning
  - surrogate
  - SWAN
  - GA
aliases:
  - Entrega 8 dos Blueprints
  - Blueprint Train Model
created: 2026-05-16
status: entrega-8
---

# BLUEPRINT_06_TRAIN_MODEL

> Especificação operacional do ficheiro responsável por treinar o surrogate a partir dos datasets congelados, separando claramente a baseline operacional do modo B da trilha de treino mais pesada do modo C.

## Objetivo do ficheiro

Este ficheiro recebe apenas datasets congelados e artefactos de configuração, e transforma esses dados em modelos treinados, versionados e auditáveis.

O seu papel não é reconstruir datasets, não é reler outputs brutos do SWAN e não é decidir novamente se um caso entra ou sai do treino. Esse trabalho já foi fechado na fase anterior.

O objetivo aqui é treinar de forma reproduzível, com contratos claros de input, output, métricas, artefactos e critérios de bloqueio.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_05_BUILD_DATASET.md` produz datasets congelados B e C
2. `BLUEPRINT_06_TRAIN_MODEL.md` treina modelos a partir desses datasets
3. `BLUEPRINT_07_VALIDATE_MODEL.md` valida o comportamento do surrogate fora do treino

Se este ficheiro voltar a misturar parsing, merge ou limpeza de dados, o pipeline perde rastreabilidade e reprodutibilidade.

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `training.split`
- `training.random_seed`
- `fitness.normalization`
- `fitness.p_total_bounds`
- `fitness.hra_bounds`
- `hra.mode`

### Input 2 — `config/paths.yaml`

O ficheiro deve usar:
- `processed_dir`
- `models_dir`
- `reports_dir`
- `logs_dir`

### Input 3 — dataset congelado do modo B

Ficheiro esperado:

```text
data/processed/dataset_B_vX.csv
```

### Input 4 — dataset congelado do modo C

Ficheiro esperado:

```text
data/processed/dataset_C_index_vX.csv
```

### Input 5 — `dataset_registry.yaml`

O treino deve ler o registry para saber:
- que versão de dataset está a consumir
- que política de split foi usada ou será usada
- que bounds de normalização estão associados ao dataset
- que contratos B e C estão ativos

## Outputs produzidos

### Outputs principais do modo B

Ficheiros sugeridos:

```text
models/model_B_p_total_vX.pkl
models/model_B_hra_vX.pkl
models/model_B_bundle_vX.pkl
```

### Outputs principais do modo C

Ficheiros sugeridos:

```text
models/model_C_field_vX.pt
models/model_C_bundle_vX.pt
```

### Outputs auxiliares obrigatórios

1. `models/train_registry.yaml`
2. `reports/train_metrics_B.yaml`
3. `reports/train_metrics_C.yaml`
4. `reports/train_curves/`
5. `reports/logs/06_train_model.log`

### Função de cada output auxiliar

- `train_registry.yaml`: regista dataset usado, configuração, seed, modelo e artefactos produzidos
- `train_metrics_B.yaml`: métricas do treino B
- `train_metrics_C.yaml`: métricas do treino C
- `train_curves/`: curvas e gráficos associados ao treino
- log: sequência operacional do treino

## Regra central do ficheiro

O treino só pode consumir datasets congelados e versionados. Não é permitido refazer merge, recalcular HRA a partir de campos brutos ou reinterpretar outputs do SWAN dentro deste ficheiro.

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_dataset_registry()`

Lê e valida o `dataset_registry.yaml`.

### 2. `load_dataset_for_mode(mode)`

Carrega o dataset congelado correto para B ou C.

### 3. `build_train_val_test_split()`

Cria os splits de forma reprodutível quando a política escolhida for split no treino.

### 4. `fit_input_scaler()`

Ajusta o scaler dos inputs usando apenas o conjunto de treino.

### 5. `prepare_targets_for_mode(mode)`

Organiza os targets conforme o contrato do modo B ou C.

### 6. `train_mode_B_baseline()`

Treina a baseline operacional do modo B.

### 7. `train_mode_B_mlp_optional()`

Treina a alternativa MLP do modo B, apenas se a baseline não atingir o objetivo.

### 8. `train_mode_C_field_model()`

Treina a trilha do modo C para campo completo.

### 9. `evaluate_training_metrics()`

Calcula métricas no treino, validação e teste conforme o modo.

### 10. `write_training_artifacts()`

Guarda modelos, scalers, métricas, plots e registry do treino.

## Fluxo interno

### Etapa 1 — carregar registry, configs e datasets

Ler `problem.yaml`, `paths.yaml`, `dataset_registry.yaml` e os datasets congelados selecionados.

### Etapa 2 — validar coerência do contrato

Confirmar que:
- `n_wecs` bate com o dataset
- os bounds de normalização existem
- o modo pedido está disponível no registry
- a versão do dataset é explícita

### Etapa 3 — construir splits

Aplicar a política definida no registry. Se o split ainda não existir, gerar de forma reproduzível usando `random_seed`.

### Etapa 4 — ajustar pré-processamento

Ajustar scalers e transformações usando apenas o conjunto de treino.

### Etapa 5 — treinar modelos

Treinar o modo B e o modo C como trilhas separadas, ainda que o mesmo script possa suportar ambos.

### Etapa 6 — calcular métricas e guardar artefactos

Gerar métricas, bundles de modelo, registos do treino e gráficos obrigatórios.

## Contrato de inputs do treino

### Inputs do modo B

O vetor de input do modo B é:

```text
[x1, y1, x2, y2, ..., xN, yN, Hs, Tp, Dir]
```

### Targets do modo B

Os targets do modo B são:

```text
P_total
HRA_area_1, ..., HRA_area_k
```

### Inputs do modo C

O input do modo C é o mesmo vetor tabular do modo B.

### Targets do modo C

Os targets do modo C são:
- `P_total`
- campo completo de `Hs`, lido a partir do artefacto indexado em `dataset_C_index_vX.csv`

## Política de split

### Regra mínima

O split deve respeitar o contrato do `problem.yaml` e do `dataset_registry.yaml`.

### Regra de reprodutibilidade

O split deve ser determinístico dado o `random_seed` e a versão do dataset.

### Recomendação prática

Guardar um artefacto com os `case_id` pertencentes a treino, validação e teste. Isso evita que duas corridas futuras usem partições diferentes sem perceber.

Ficheiros sugeridos:

```text
models/splits/B_split_vX.yaml
models/splits/C_split_vX.yaml
```

## Pré-processamento dos inputs

### Regra

Scalers ou normalizadores dos inputs devem ser ajustados apenas no conjunto de treino.

### Artefactos a guardar

- scaler dos inputs do modo B
- scaler dos inputs do modo C, se diferente
- ordem exata das features

### Observação

Sem guardar a ordem das features, a exportação e o uso no GA tornam-se frágeis.

## Normalização dos targets e da fitness

### Regra principal

`P_total` e HRA devem permanecer em unidades físicas no dataset congelado.

### Regra operacional

A normalização min-max para `[0.01, 1]` é parte do contrato da fitness e deve ser preservada como artefacto do bundle do modelo, não aplicada de forma opaca e irreproduzível.

### Consequência prática

O treino pode usar targets físicos e aplicar normalização só onde fizer sentido para a arquitetura ou para a interface do GA, mas os bounds usados têm de vir do contrato congelado do dataset.

## Trilha do modo B

### Papel do modo B

O modo B é a baseline operacional do projeto.

### Modelo baseline

A baseline preferida é XGBoost para `P_total` e para HRA, usando regressão separada por target ou um esquema multi-output leve, consoante estabilidade e simplicidade operacional.

### Modelo alternativo

MLP em PyTorch entra apenas se a baseline não atingir as métricas desejadas ou se houver ganho claro em generalização.

### Recomendação operacional

Começar com duas subtrilhas bem simples:
- modelo para `P_total`
- modelo para vetor HRA

Isto reduz acoplamento e facilita depuração.

## Trilha do modo C

### Papel do modo C

O modo C é uma trilha separada, não uma extensão trivial do B.

### Natureza do problema

Aqui o target já não é apenas escalar ou vetorial curto. O target inclui um campo espacial completo de `Hs`.

### Requisitos mínimos

- grid fixo e documentado
- loader do campo por `hs_field_file`
- estratégia explícita para representar o campo no backend de treino
- preservação de `grid_id` e `field_shape`

### Opções de modelação

O blueprint não fecha uma única arquitetura, mas exige que a primeira versão explicite se vai usar:
- regressão sobre campo achatado
- compressão do campo antes da regressão
- modelo neural de saída espacial

### Regra de prudência

Se o objetivo imediato for reduzir risco operacional, o modo B deve ser fechado primeiro. O modo C pode avançar em paralelo, mas não deve atrasar o uso prático do surrogate.

## Métricas obrigatórias do modo B

### Métricas mínimas

- RMSE
- MAE
- R²
- MAPE, se numericamente apropriado
- Spearman de ranking
- erro no top 10% dos layouts por desempenho

### Regra importante

O erro médio global não basta. O treino deve reportar explicitamente o comportamento na região de layouts que o otimizador mais vai explorar.

## Métricas obrigatórias do modo C

### Métricas mínimas

- RMSE espacial do campo
- MAE espacial do campo
- erro no `P_total`
- erro no HRA reconstituído a partir do campo
- erro em regiões críticas do domínio

### Regra importante

O modo C não pode ser aprovado apenas porque reconstrói bem médias globais. O campo precisa de manter estrutura espacial útil.

## Gráficos obrigatórios

### Para o modo B

Guardar em `reports/train_curves/` ou equivalente:
- predito vs real para `P_total`
- predito vs real para cada HRA
- histograma de erro
- erro por faixa de `Hs`
- erro por faixa de `Tp`
- erro por família geométrica

### Para o modo C

Guardar também:
- mapas de erro espacial
- exemplos de campo real vs predito
- erro do HRA reconstituído por área

## Critérios de bloqueio do modo B

O modelo B não deve seguir para validação final se acontecer pelo menos um destes casos:
- falha em produzir ranking útil
- erro excessivo no top 10%
- grande sensibilidade a mudanças pequenas de split
- necessidade de pós-processamento corretivo silencioso para manter outputs físicos

## Critérios de bloqueio do modo C

O modelo C não deve seguir para validação final se acontecer pelo menos um destes casos:
- campo reconstruído sem coerência espacial útil
- incapacidade de reconstituir HRA com erro aceitável
- artefactos instáveis entre corridas equivalentes
- custo desproporcional sem ganho claro face ao objetivo atual

## Contrato do bundle do modelo

Cada modelo treinado deve ser acompanhado por um bundle com, no mínimo:

```yaml
model_version: "v1"
problem_id: "swan_surrogate_n28_v1"
dataset_version: "v1"
mode: "B"
input_features:
  - x1
  - y1
  - x2
  - y2
  - Hs
  - Tp
  - Dir
input_scaler_file: "..."
model_file: "..."
fitness_bounds:
  p_total_bounds: [0.0, 1.0]
  hra_bounds: [0.0, 1.0]
metrics_file: "..."
created_at: "..."
```

### Regra

Sem bundle, o modelo não está pronto para exportação segura nem para integração no GA.

## Contrato de `train_registry.yaml`

Este ficheiro deve guardar, no mínimo:

```yaml
training_run_id: "train_B_v1"
dataset_version: "v1"
problem_id: "swan_surrogate_n28_v1"
modes_trained:
  B: true
  C: true
random_seed: 42
split_policy: "train_side_deterministic"
artifacts:
  model_B_p_total: "models/model_B_p_total_v1.pkl"
  model_B_hra: "models/model_B_hra_v1.pkl"
  model_C_field: "models/model_C_field_v1.pt"
created_at: "..."
```

## Logging

### Eventos mínimos a registar

- dataset e versão carregados
- número de casos por split
- arquitetura escolhida por modo
- início e fim de cada treino
- melhores hiperparâmetros, se houver procura
- métricas finais por split
- artefactos escritos

## Núcleo comum, modo B e modo C

### Núcleo comum

Leitura de dataset congelado, split reproduzível, scalers, registry, logs e artefactos pertencem ao núcleo comum.

### Diferença para B

O modo B é regressão tabular com baseline clara e foco operacional imediato.

### Diferença para C

O modo C é previsão de campo e precisa de uma trilha própria de representação, treino e métricas espaciais.

### Regra prática

O mesmo script pode implementar B e C, mas internamente deve tratá-los como pipelines distintos, não como duas flags superficiais no mesmo treino.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_05_BUILD_DATASET.md`
- datasets congelados válidos e versionados

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- leia datasets congelados e o dataset registry
- gere splits reproduzíveis
- treine a baseline B
- suporte a trilha C sem ambiguidade de contrato
- produza bundles, métricas, logs e registry de treino
- preserve os bounds da normalização da fitness como artefacto versionado

## Riscos e armadilhas

### Armadilha 1

Refazer merges ou parsing dentro do treino. Isso quebra a separação de responsabilidades.

### Armadilha 2

Tratar o modo C como se fosse apenas “mais targets” do modo B. Não é.

### Armadilha 3

Ajustar scalers usando treino mais validação ou treino mais teste. Isso contamina as métricas.

### Armadilha 4

Não guardar os splits por `case_id`. Isso torna difícil reproduzir resultados mais tarde.

### Armadilha 5

Guardar só o modelo e esquecer o bundle completo com bounds, ordem das features e versão do dataset.

## Checklist de implementação futura

- [ ] carregar `dataset_registry.yaml`
- [ ] carregar `dataset_B_vX.csv` quando aplicável
- [ ] carregar `dataset_C_index_vX.csv` quando aplicável
- [ ] validar coerência do contrato
- [ ] gerar ou carregar splits reproduzíveis
- [ ] ajustar scalers no treino apenas
- [ ] treinar baseline B
- [ ] treinar alternativa MLP de B apenas se necessário
- [ ] treinar trilha C com contrato explícito
- [ ] calcular métricas por split
- [ ] gerar gráficos obrigatórios
- [ ] escrever bundles e modelos
- [ ] escrever `train_registry.yaml`
- [ ] guardar logs

## Ligações

- [[BLUEPRINT_05_BUILD_DATASET]]
- [[BLUEPRINT_07_VALIDATE_MODEL]]
- [[BLUEPRINT_08_EXPORT_SURROGATE]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
