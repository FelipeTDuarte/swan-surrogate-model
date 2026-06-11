---
tags:
  - blueprint
  - config
  - schema
  - surrogate
  - SWAN
  - GA
aliases:
  - Entrega 2 dos Blueprints
  - Blueprint Config Global
created: 2026-05-16
status: entrega-2
---

# BLUEPRINT_CONFIG_GLOBAL

> Documento mestre dos contratos globais do surrogate SNL-SWAN. Tudo o que os outros blueprints assumem como formato, regra, schema ou convenção nasce aqui.

## Função deste documento

Este documento fecha os contratos globais usados por todos os ficheiros do pipeline.

Sem este documento, cada script tenderia a inventar o seu próprio formato para caminhos, casos, datasets, outputs, logs e metadados.

O objetivo aqui é impedir essa deriva e tornar a implementação previsível, auditável e reprodutível.

## Lugar no pipeline

Este é o primeiro blueprint técnico real da sequência. Todos os blueprints seguintes dependem deste ficheiro.

Se alguma regra definida aqui mudar, os blueprints de geração, parsing, dataset, treino, validação, exportação e uso no GA podem precisar de revisão.

## Âmbito

Este documento cobre:
- contratos de configuração
- schemas de identificação de casos
- ordenação canónica dos layouts
- contratos dos modos B e C
- schemas de datasets e metadados
- regras de compatibilidade de dados históricos
- regras mínimas de logging e validação global

Este documento não descreve a lógica interna de cada script. Isso fica para os blueprints específicos.

## Convenções gerais

### Convenção 1 — número de WECs

O número de WECs é fixo por surrogate. Um modelo treinado para `N=28` não serve para `N=24` nem para `N=30`.

Se o problema mudar de N, cria-se um novo dataset, um novo treino e uma nova versão de modelo.

### Convenção 2 — geometria válida

A validade geométrica do layout é determinada pelo código de restrições do GA já existente.

Esse código é a fonte de verdade para:
- área admissível
- distância mínima entre WECs
- rejeição de layouts inválidos

Pode existir um verificador auxiliar independente no pipeline de dados, mas apenas como camada de auditoria. Nunca como substituto silencioso da lógica principal.

### Convenção 3 — ordenação canónica dos WECs

Todo layout deve ser convertido para uma ordem canónica antes de:
- ser guardado como caso
- ser comparado com outro layout
- entrar no dataset
- entrar no surrogate em inferência

A regra canónica padrão é:
1. ordenar por `x` crescente
2. em empate, ordenar por `y` crescente

Isto evita que o mesmo parque físico apareça com várias codificações diferentes.

### Convenção 4 — sistema de coordenadas

Todas as posições devem usar o mesmo sistema local de coordenadas definido no problema. Não misturar coordenadas locais com geográficas.

As unidades de posição são metros.

### Convenção 5 — estados de mar

O estado de mar mínimo usado pelo surrogate é o triplo:
- `Hs`
- `Tp`
- `Dir`

Se no futuro fores acrescentar parâmetros como spreading, corrente ou outro descritor, isso exige uma nova revisão deste contrato.

### Convenção 6 — batimetria e domínio

Batimetria, domínio de propagação, resolução do grid, templates fixos do SWAN e definições estruturais do modelo são considerados constantes dentro de um surrogate.

Se algum destes elementos mudar, não se trata de mero retreino incremental. Trata-se de um problema diferente.

## Contrato de `config/paths.yaml`

### Objetivo

Centralizar todos os caminhos externos e internos necessários ao pipeline.

### Schema obrigatório

```yaml
swan_executable: "/path/to/snl-swan/swan.exe"
swan_template_dir: "/path/to/templates/"
runs_dir: "./data/raw/"
processed_dir: "./data/processed/"
models_dir: "./models/"
reports_dir: "./reports/"
logs_dir: "./reports/logs/"
archive_dir: "./data/archive/"
```

### Regras

- todos os caminhos devem ser absolutos ou resolvidos relativamente à raiz do projeto
- o pipeline não deve espalhar caminhos hardcoded pelos scripts
- a criação automática de diretórios pode acontecer, mas nunca silenciosamente sem log

### Critérios de aceite

`paths.yaml` é válido se:
- todos os campos obrigatórios existirem
- o executável do SWAN existir e for acessível
- as pastas de output puderem ser criadas

## Contrato de `config/problem.yaml`

### Objetivo

Definir o problema físico, geométrico, estatístico e operacional do surrogate.

### Schema obrigatório

```yaml
problem_id: "swan_surrogate_n28_v1"

n_wecs: 28
wec_type: "WaveRoller_X"

geometry:
  x_min: 0.0
  x_max: 2000.0
  y_min: 0.0
  y_max: 1500.0
  min_wec_spacing: 50.0
  ordering: "sort_by_x_then_y"

sea_state:
  Hs_min: 0.5
  Hs_max: 4.0
  Tp_min: 5.0
  Tp_max: 16.0
  Dir_min: 220.0
  Dir_max: 320.0
  sampling_mode: "importance_from_scatter"

hra:
  mode: "multi_area"
  aggregation: "mean"
  areas:
    - name: "area_1"
      polygon: [[500,200],[1800,200],[1800,800],[500,800]]
    - name: "area_2"
      polygon: [[200,100],[700,100],[700,500],[200,500]]

storage:
  save_full_mat: true
  save_area_mats: true

training:
  n_pilot_samples: 500
  n_training_samples: 15000
  split:
    train: 0.70
    val: 0.15
    test: 0.15
  random_seed: 42

fitness:
  normalization: "minmax_0.01_1"
  p_total_bounds: [0.0, 1.0]
  hra_bounds: [0.0, 1.0]
```

### Regras

- `n_wecs` deve ser inteiro positivo
- `min_wec_spacing` deve ser maior que zero
- `Hs_min < Hs_max`, `Tp_min < Tp_max`, `Dir_min < Dir_max`
- os polígonos das áreas HRA devem ser válidos e fecháveis
- `split.train + split.val + split.test = 1.0`
- os bounds da normalização do fitness devem existir e ser versionados com o modelo

### Observação crítica

Os campos `fitness.p_total_bounds` e `fitness.hra_bounds` não são “verdades físicas universais”. São os bounds operacionais congelados usados para a normalização min-max no projeto.

Se forem recalculados, isso gera uma nova versão do contrato.

## Contrato de identificação dos casos

### Campo `case_id`

Cada simulação deve ter um identificador único, estável e legível.

Formato recomendado:

```text
CASE_N{N}_L{layout_idx:06d}_S{sea_idx:06d}
```

Exemplo:

```text
CASE_N28_L000137_S000022
```

### Regras do `case_id`

- o `case_id` nunca muda depois de atribuído
- o `case_id` deve ser usado como chave principal em todos os merges
- o `case_id` não deve carregar significado físico além da identificação do caso

## Contrato do layout

### Forma interna padrão

Durante o processamento, o layout deve existir na forma:

```python
layout.shape == (N, 2)
```

onde cada linha representa:

```python
[x_i, y_i]
```

### Forma tabular para dataset

No dataset, o layout deve ser expandido para colunas fixas:

```text
x1, y1, x2, y2, ..., xN, yN
```

### Regras

- nunca misturar forma matricial e forma achatada sem conversão explícita
- qualquer função que receba layout deve declarar a forma esperada
- todo layout tabular deve já estar em ordem canónica

## Contrato do estado de mar

### Forma interna padrão

```python
sea_state.shape == (3,)
```

na ordem:

```python
[Hs, Tp, Dir]
```

### Forma tabular para dataset

Colunas:

```text
Hs, Tp, Dir
```

### Regras

- a ordem é fixa e nunca muda
- unidades: `Hs` em metros, `Tp` em segundos, `Dir` em graus
- valores fora do envelope treinado não devem ser aceites em inferência sem alerta

## Contrato do modo B

### Definição

No modo B, o surrogate prevê:
- `P_total`
- vetor curto de HRA em áreas explícitas

Formalmente:

```python
y_B = [P_total, HRA_area_1, ..., HRA_area_k]
```

### Quando usar

- quando as áreas de interesse já estão fechadas
- quando o objetivo principal é operacionalizar rápido
- quando queres custo de treino e inferência mais baixos

### Requisitos mínimos dos dados

Cada caso válido para B precisa de:
- layout válido
- `Hs`, `Tp`, `Dir`
- `P_total`
- HRA calculável para cada área definida, ou `.mat` suficiente para o recalcular

### Dataset do modo B

Formato base de linha:

```text
case_id, x1, y1, ..., xN, yN, Hs, Tp, Dir, P_total, HRA_area_1, ..., HRA_area_k
```

## Contrato do modo C

### Definição

No modo C, o surrogate prevê:
- `P_total`
- campo completo de `Hs` no domínio de referência

Formalmente:

```python
y_C = [P_total, Hs_field]
```

onde `Hs_field` é um array 2D ou uma vectorização equivalente num grid fixo e documentado.

### Quando usar

- quando queres flexibilidade máxima
- quando queres recalcular HRA em novas áreas sem nova simulação
- quando queres preparar terreno para um surrogate de campo completo

### Requisitos mínimos dos dados

Cada caso válido para C precisa de:
- layout válido
- `Hs`, `Tp`, `Dir`
- `P_total`
- `.mat` completo do domínio
- informação suficiente para mapear o campo ao grid de referência

### Dataset do modo C

O dataset C deve ser dividido em duas partes:

1. índice tabular do caso
2. armazenamento do campo em ficheiro associado

Formato do índice:

```text
case_id, x1, y1, ..., xN, yN, Hs, Tp, Dir, P_total, hs_field_file
```

## Regra de compatibilidade entre B e C

Todo caso válido para C também deve ser potencialmente reaproveitável para B, desde que as áreas HRA sejam definidas.

O inverso não é verdade. Um caso válido para B não é automaticamente válido para C.

## Contrato dos ficheiros `.mat`

### Regra geral

Sempre que possível, guardar o `.mat` bruto original do SWAN sem perda.

### Campos mínimos esperados

O blueprint específico de parsing vai fechar os nomes exactos, mas o contrato global exige que seja possível recuperar:
- campo de `Hs`
- grelha espacial correspondente, se necessário
- metadados mínimos para mapear o campo ao domínio

### Regras

- o `.mat` bruto não deve ser sobrescrito depois do parsing
- recortes por área podem existir, mas nunca como único artefacto guardado se `save_full_mat = true`
- o armazenamento do `.mat` é parte do contrato de reprodutibilidade

## Contrato dos metadados por caso

Cada caso simulado deve ter metadados mínimos normalizados.

### Schema mínimo

```yaml
case_id: "CASE_N28_L000137_S000022"
problem_id: "swan_surrogate_n28_v1"
run_status: "OK"
runtime_sec: 42.7
error_msg: null
hash_input: "..."
layout_ordering: "sort_by_x_then_y"
mode_compatibility:
  valid_for_B: true
  valid_for_C: true
files:
  swn_input: "..."
  swan_stdout: "..."
  hs_mat: "..."
```

### Regras

- metadados devem existir mesmo para casos falhados
- `run_status` não pode ser inferido implicitamente por ausência de erro
- `mode_compatibility` deve ser decidido após parsing e sanity checks

## Contrato do dataset congelado

O dataset de treino não deve ser reconstruído ad hoc em memória sempre que alguém quiser treinar. Deve haver um dataset congelado e versionado.

### Dataset congelado B

Ficheiro sugerido:

```text
data/processed/dataset_B_v1.csv
```

### Dataset congelado C

Ficheiro sugerido:

```text
data/processed/dataset_C_index_v1.csv
```

mais a pasta de campos associada.

### Regra de versionamento

Sempre que mudares qualquer um destes elementos, cria nova versão de dataset:
- área HRA
- envelope de estados de mar
- política de limpeza do `.mat`
- regras de inclusão de casos
- bounds de normalização ligados ao dataset

## Contrato de compatibilidade de dados históricos

### Caso histórico válido para uso em treino

Um caso histórico só pode entrar no repositório de treino se tiver:
- layout completo
- número de WECs
- `Hs`, `Tp`, `Dir`
- output de `P_total`
- identificação única
- estado de execução conhecido
- referência ao input original ou equivalente reconstituível

Para B, precisa ainda de HRA calculável ou `.mat` suficiente.

Para C, precisa obrigatoriamente do `.mat` completo do domínio no formato reaproveitável.

### Caso histórico inválido

Um caso histórico deve ficar fora do treino se:
- faltar layout completo
- faltar identificação inequívoca
- faltar estado de mar
- não houver garantia de correspondência entre input e output
- o `.mat` estiver ausente para treino C
- a área HRA antiga não for compatível nem recalculável

## Contrato global de logging

Todos os scripts devem produzir logs minimamente compatíveis.

### Campos mínimos por evento relevante

```text
timestamp, level, script_name, case_id, message
```

### Níveis mínimos

- `INFO`
- `WARNING`
- `ERROR`

### Regra

Nenhum erro estrutural importante deve acontecer silenciosamente.

## Contrato global de validação

Existem validações que pertencem aos scripts específicos, mas há um conjunto mínimo global.

### Validações globais obrigatórias

- schema de `paths.yaml`
- schema de `problem.yaml`
- ordenação canónica antes de persistência
- unicidade de `case_id`
- consistência entre `n_wecs` e número de colunas do layout
- consistência entre modo selecionado e artefactos disponíveis

## Tripwires globais

### Tripwire 1

Se o mesmo layout físico aparecer duas vezes com ordem diferente, o pipeline está inconsistente.

### Tripwire 2

Se um caso entrar como válido para C sem `.mat` completo reaproveitável, o pipeline está inconsistente.

### Tripwire 3

Se os bounds da normalização do fitness mudarem sem nova versão de dataset ou modelo, a rastreabilidade foi quebrada.

### Tripwire 4

Se `problem.yaml` permitir um modo que os ficheiros seguintes não suportam, há buraco de contrato.

## Dependências deste blueprint

Este documento depende de:
- [[surrogate_swan_plano_v2_auditado]]
- [[BLUEPRINTS_DELIVERY_PLAN]]
- [[BLUEPRINTS_INDEX]]

## Impacto nos blueprints seguintes

Tudo o que vem a seguir deve referenciar este documento quando usar:
- schemas
- nomes de campos
- convenções de ordering
- definição de modo B ou C
- regras de versionamento

## Critérios de aceite

Este blueprint só é considerado fechado se:
- permitir especificar os próximos blueprints sem ambiguidade de formatos
- deixar claro o que é caso válido para B e para C
- fixar ordenação canónica, metadados e contratos de dataset
- fechar o contrato de configuração e normalização do fitness

## Riscos e armadilhas

O risco mais comum nesta fase é tratar formatos como detalhes implementativos. Aqui eles não são detalhes. Eles são contrato.

Outro risco é tentar adiar a definição formal dos modos B e C. Se isso acontecer, os blueprints de parsing, dataset, treino e exportação ficam todos instáveis.

## Ligações

- [[BLUEPRINTS_INDEX]]
- [[BLUEPRINT_01_GENERATE_LAYOUTS]]
- [[BLUEPRINT_04_PARSE_OUTPUTS]]
- [[BLUEPRINT_05_BUILD_DATASET]]
- [[BLUEPRINT_06_TRAIN_MODEL]]
