---
tags:
  - blueprint
  - data-pipeline
  - layouts
  - surrogate
  - SWAN
  - GA
aliases:
  - Entrega 3 dos Blueprints
  - Blueprint Generate Layouts
created: 2026-05-16
status: entrega-3
---

# BLUEPRINT_01_GENERATE_LAYOUTS

> Especificação operacional do ficheiro responsável por gerar layouts válidos de WECs e associar estados de mar candidatos para o dataset de treino do surrogate.

## Objetivo do ficheiro

Este ficheiro gera os casos candidatos que alimentam o pipeline de simulação. O seu papel não é correr o SWAN, nem calcular outputs, nem montar o dataset final. O seu papel é produzir uma base de casos **válidos, diversos, rastreáveis e compatíveis** com os contratos globais já fechados.

O ficheiro deve produzir layouts fisicamente admissíveis, já em ordem canónica, sem duplicações e com estados de mar amostrados dentro do envelope operacional definido no `problem.yaml`.

## Lugar no pipeline

Este ficheiro é o primeiro passo operacional do pipeline de dados.

A sequência lógica é:
1. `BLUEPRINT_CONFIG_GLOBAL.md` define contratos e schemas
2. `BLUEPRINT_01_GENERATE_LAYOUTS.md` gera casos candidatos válidos
3. `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` transforma esses casos em runs do SNL-SWAN

Se este ficheiro gerar casos mal estruturados, todos os passos seguintes herdam o erro.

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `geometry`
- `sea_state`
- `training`
- `hra.mode`

### Input 2 — `config/paths.yaml`

Deve ler os caminhos necessários para gravar saídas em `processed_dir` e logs em `logs_dir`.

### Input 3 — fonte da scatter diagram

Se `sampling_mode = importance_from_scatter`, o ficheiro deve conseguir ler uma fonte de distribuição dos estados de mar. Essa fonte pode ser:
- CSV
- Parquet
- tabela já agregada em bins
- outro formato estruturado definido em configuração adicional

O formato exato da scatter diagram pode ser fechado mais tarde num anexo de config, mas este blueprint exige que a leitura seja explícita e validada.

### Input 4 — código de validação geométrica

O ficheiro deve usar o código de restrições geométricas já existente no teu GA como fonte principal de verdade para validar layouts.

## Outputs produzidos

### Output principal

`data/processed/candidates.csv`

Este ficheiro deve conter uma linha por caso candidato, com pelo menos:

```text
case_id, layout_id, sea_state_id, x1, y1, x2, y2, ..., xN, yN, Hs, Tp, Dir, layout_family
```

### Outputs auxiliares

1. `data/processed/layout_bank.csv`
2. `data/processed/sea_state_bank.csv`
3. `reports/logs/01_generate_layouts.log`
4. `reports/layout_generation_summary.yaml`

### Função de cada output auxiliar

- `layout_bank.csv`: banco de layouts únicos antes da combinação com estados de mar
- `sea_state_bank.csv`: banco de estados de mar amostrados
- log: registo de avisos, rejeições e estatísticas
- summary: métricas agregadas da geração

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_problem_config()`

Carrega e valida `problem.yaml`.

### 2. `load_paths_config()`

Carrega e valida `paths.yaml`.

### 3. `sample_layout_candidates()`

Gera candidatos brutos de layout antes da validação final.

### 4. `canonicalize_layout(layout)`

Aplica a ordenação canónica obrigatória.

### 5. `is_layout_valid(layout)`

Usa o validador geométrico principal para confirmar viabilidade.

### 6. `deduplicate_layout(layout)`

Converte o layout numa representação hashável estável para detectar duplicatas depois da ordenação canónica.

### 7. `sample_sea_states()`

Amostra estados de mar dentro do envelope definido, com a política configurada.

### 8. `combine_layouts_and_sea_states()`

Combina o banco de layouts e o banco de estados de mar para produzir casos finais.

### 9. `build_case_id()`

Gera o `case_id` seguindo o contrato global.

### 10. `write_candidates_outputs()`

Persiste `candidates.csv`, `layout_bank.csv`, `sea_state_bank.csv` e `summary.yaml`.

## Fluxo interno

O fluxo interno recomendado é este.

### Etapa 1 — carregar configurações

Ler `problem.yaml` e `paths.yaml`, validar schemas e criar os diretórios necessários.

### Etapa 2 — preparar geradores

Inicializar o gerador aleatório com `random_seed`, carregar a scatter diagram se aplicável, e preparar as famílias geométricas que serão impostas ao dataset.

### Etapa 3 — gerar layouts candidatos

Gerar layouts brutos usando mistura controlada de famílias geométricas. O ficheiro não deve depender só de layouts aleatórios sem estrutura.

### Etapa 4 — validar layouts

Aplicar, por ordem:
1. ordenação canónica
2. validação geométrica
3. deduplicação

Só layouts aprovados entram no banco de layouts.

### Etapa 5 — gerar estados de mar

Gerar o banco de estados de mar dentro do envelope definido. Quando o modo for `importance_from_scatter`, amostrar de acordo com a distribuição observada, e não uniformemente em todo o espaço.

### Etapa 6 — combinar layout e estado de mar

Produzir os casos candidatos finais. Cada caso final precisa de `case_id`, `layout_id` e `sea_state_id`.

### Etapa 7 — persistir outputs e estatísticas

Guardar ficheiros tabulares e resumo da geração.

## Política de amostragem dos layouts

### Objetivo

Não gerar apenas layouts aleatórios, mas um conjunto que cubra formas que o GA realmente tende a explorar.

### Famílias obrigatórias de layout

O ficheiro deve incluir percentagens configuráveis de layouts vindos de famílias distintas.

#### Família F1 — aleatória dispersa

WECs distribuídos aleatoriamente na área admissível, respeitando as restrições geométricas.

#### Família F2 — quase grelha

Layouts próximos de uma malha regular, com pequena perturbação aleatória.

#### Família F3 — fileiras alinhadas

Layouts organizados em linhas aproximadamente paralelas.

#### Família F4 — diagonais / enviesadas

Layouts com orientação principal diagonal.

#### Família F5 — compactas

Layouts com maior concentração espacial, ainda respeitando o espaçamento mínimo.

#### Família F6 — dispersas

Layouts espalhados por grande parte da área admissível.

### Regra operacional

O resumo final da geração deve indicar quantos layouts vieram de cada família.

## Política de amostragem dos estados de mar

### Modo recomendado

`importance_from_scatter`

### Regra

O gerador deve amostrar mais densamente nas regiões da scatter diagram com maior frequência de ocorrência, mas mantendo alguma cobertura do envelope operacional total.

### Resultado esperado

Evitar dois problemas:
- sobrecobrir regiões raras do espaço
- subcobrir regiões onde o GA vai passar a maior parte do tempo operacional

### Campos mínimos do banco de estados de mar

```text
sea_state_id, Hs, Tp, Dir, source_bin, source_weight
```

## Validações obrigatórias

### Validações de configuração

- `n_wecs` coerente com o problema
- `min_wec_spacing > 0`
- envelopes de `Hs`, `Tp` e `Dir` válidos
- `n_training_samples > 0`
- caminhos de output acessíveis

### Validações dos layouts

- todos os WECs dentro da área admissível
- respeito do espaçamento mínimo
- shape correto `(N, 2)`
- ordenação canónica aplicada
- ausência de duplicação depois da ordenação

### Validações dos estados de mar

- `Hs`, `Tp`, `Dir` dentro do envelope configurado
- pesos de amostragem finitos
- bins válidos na scatter diagram

### Validações do output final

- unicidade de `case_id`
- consistência entre `layout_id` e layout tabular
- consistência entre `sea_state_id` e `Hs, Tp, Dir`
- número final de casos igual ao planeado ou justificado no resumo

## Estratégia de deduplicação

A deduplicação não deve ser feita sobre o layout cru. Deve ser feita sobre o layout canónico.

### Regra

1. converter layout para ordem canónica
2. arredondar coordenadas com tolerância definida
3. criar assinatura hashável estável
4. rejeitar duplicatas

### Observação

Sem este passo, o mesmo parque físico pode entrar várias vezes com permutações diferentes e contaminar o treino.

## Estratégia de identificação

### `layout_id`

Formato sugerido:

```text
LAY_N{N}_{family}_{idx:06d}
```

Exemplo:

```text
LAY_N28_grid_000143
```

### `sea_state_id`

Formato sugerido:

```text
SEA_{idx:06d}
```

### `case_id`

Formato obrigatório global:

```text
CASE_N{N}_L{layout_idx:06d}_S{sea_idx:06d}
```

## Estratégia de combinação layout × estado de mar

O blueprint não impõe uma única estratégia de cartesian product completo. O objetivo é controlar o volume sem perder cobertura.

### Estratégia recomendada

1. gerar um banco de layouts válidos
2. gerar um banco de estados de mar válidos
3. combinar por amostragem controlada até atingir `n_training_samples`

Isto evita explosão combinatória desnecessária.

### Regra importante

Se o mesmo layout for combinado com muitos estados de mar, isso deve ser intencional e rastreável. O resumo da geração deve mostrar essa distribuição.

## Regras de logging

### Eventos que devem ser logados

- início da geração
- carregamento da configuração
- número de layouts tentados
- número de layouts rejeitados
- motivo principal das rejeições
- número de layouts únicos aceites
- número de estados de mar gerados
- número final de casos candidatos
- warnings sobre baixa diversidade

### Motivos mínimos de rejeição a contabilizar

- fora da área admissível
- violação do espaçamento mínimo
- duplicado após ordenação
- erro de shape
- estado de mar fora do envelope

## Summary obrigatório

O ficheiro `reports/layout_generation_summary.yaml` deve conter, no mínimo:

```yaml
problem_id: "..."
n_wecs: 28
n_layouts_attempted: 20000
n_layouts_valid: 5000
n_layouts_unique: 4200
n_layouts_rejected: 15000
layout_family_counts:
  random_sparse: 1200
  grid_like: 700
  row_aligned: 800
  diagonal: 500
  compact: 500
  dispersed: 500
n_sea_states_generated: 3000
n_cases_final: 15000
rejection_reasons:
  outside_domain: 1000
  spacing_violation: 9000
  duplicate: 4500
  malformed: 500
```

## Núcleo comum, modo B e modo C

### Núcleo comum

Este ficheiro é quase totalmente comum aos modos B e C. A geração dos candidatos não muda de forma estrutural entre os modos.

### Diferença para B

No modo B, o volume de casos pode ser planeado com foco em targets escalares ou vetoriais curtos.

### Diferença para C

No modo C, pode ser necessário privilegiar diversidade espacial maior dos layouts, porque o target final é um campo completo. Isso pode justificar maior cobertura geométrica antes mesmo do treino.

### Impacto nos ficheiros seguintes

- `02_build_swan_inputs.py` depende diretamente do formato de `candidates.csv`
- `04_parse_outputs.py` assume que `case_id`, `layout_id` e `sea_state_id` já estão bem definidos
- `05_build_dataset.py` herda a classificação por família geométrica e pode usá-la nos relatórios

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `problem.yaml`
- `paths.yaml`
- código existente de validação geométrica do GA

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- gere layouts válidos sem ambiguidade
- use a lógica geométrica correta como fonte de verdade
- imponha ordenação canónica
- deduplicate layouts corretamente
- produza `candidates.csv` com esquema estável
- produza estatísticas suficientes para auditar a qualidade da geração

## Riscos e armadilhas

### Armadilha 1

Gerar layouts aleatórios demais e layouts estruturados de menos. Isso cria dataset bonito em quantidade e fraco em representatividade.

### Armadilha 2

Deduplicar antes da ordenação canónica. Isso deixa passar duplicatas físicas com codificações diferentes.

### Armadilha 3

Usar a scatter diagram como mero filtro de envelope e não como guia de amostragem. Isso degrada o valor operacional do dataset.

### Armadilha 4

Tratar o resumo da geração como opcional. Sem ele, perdes visibilidade sobre diversidade e taxa de rejeição.

### Armadilha 5

Substituir silenciosamente o teu código de restrições geométricas por um verificador simplificado no pipeline. Isso quebraria a coerência entre o GA e o dataset.

## Checklist de implementação futura

- [ ] ler `problem.yaml`
- [ ] ler `paths.yaml`
- [ ] carregar scatter diagram, se aplicável
- [ ] gerar famílias geométricas configuráveis
- [ ] validar layouts com a fonte de verdade geométrica
- [ ] aplicar ordenação canónica
- [ ] deduplicar layouts
- [ ] gerar banco de estados de mar
- [ ] combinar layouts e estados de mar
- [ ] gerar `case_id`
- [ ] escrever `candidates.csv`
- [ ] escrever `layout_bank.csv`
- [ ] escrever `sea_state_bank.csv`
- [ ] escrever `summary.yaml`
- [ ] guardar logs

## Ligações

- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[BLUEPRINT_02_BUILD_SWAN_INPUTS]]
- [[BLUEPRINT_05_BUILD_DATASET]]
- [[surrogate_swan_plano_v2_auditado]]
