---
tags:
  - surrogate
  - SWAN
  - GA
  - wave-energy
  - machine-learning
  - nosso-mar
aliases:
  - Plano Surrogate SNL-SWAN
  - SWAN Surrogate GA
created: 2026-05-15
updated: 2026-05-16
status: auditado
---

# Surrogate SNL-SWAN para Loop do GA

> **Objectivo:** substituir o SNL-SWAN como motor de simulação dentro do loop de um Algoritmo Genético de optimização de parques de energia das ondas. O surrogate deve deslocar o custo para a fase offline, manter a inferência muito rápida dentro do GA, e preservar as restrições geométricas e a coerência física dos outputs.

---

## Contexto

Uma corrida típica do GA exige muitas avaliações de fitness. Mesmo com poucos estados de mar por optimização, o custo acumulado de simulação torna-se o gargalo principal.

O desenho deste plano assume um cenário fixo por optimização: o número de WECs não varia dentro do GA. Se o número de WECs mudar, treina-se um surrogate novo para esse N.

A batimetria, o domínio de propagação, os templates do SNL-SWAN e a formulação do problema permanecem fixos dentro de cada surrogate. O surrogate substitui apenas a chamada repetida ao simulador, não substitui a formulação física base nem as restrições geométricas do problema.

---

## Decisões Fechadas

| Decisão | Escolha | Observação |
|---|---|---|
| Tipo de baseline | XGBoost | Primeiro modelo de referência para outputs escalares ou vectores curtos |
| Modelo alternativo | MLP / PyTorch | Só se XGBoost não atingir as métricas desejadas |
| Inputs | `[x1,y1,...,xN,yN,Hs,Tp,Dir]` | Ordem canónica obrigatória dos WECs |
| Número de WECs | Fixo por surrogate | Um treino por N |
| Normalização do fitness | Min-max para `[0.01, 1]` | Aplicada a `P_total` e HRA antes da fitness |
| Restrições geométricas | Innegociáveis | Área admissível e distância mínima respeitadas antes de qualquer avaliação |
| Fonte de verdade das restrições | Código do GA existente | Código auxiliar só para verificação independente |
| Estados de mar | Espaço contínuo operacional | Não limitar o surrogate apenas aos clusters do k-means |
| HRA | Modos B e C disponíveis | O utilizador escolhe o contrato de output |
| Armazenamento de campo | Guardar `.mat` bruto sempre que possível | Permite reprocessamento e treino futuro sem nova simulação |

---

## O que este plano não faz

Este plano não tenta resolver o caso de N variável num único modelo. Este plano também não assume PINN como solução inicial, nem assume previsão de campo completo como baseline operacional.

O modo C existe, mas deve ser tratado como uma trilha mais pesada do que o modo B. O modo B é o caminho operacional mais simples. O modo C é o caminho com maior flexibilidade futura.

---

## Estrutura do projecto

```text
swan_surrogate_project/
├── README.md
├── config/
│   ├── paths.yaml
│   └── problem.yaml
├── src/
│   ├── 01_generate_layouts.py
│   ├── 02_build_swan_inputs.py
│   ├── 03_run_swan_batch.py
│   ├── 04_parse_outputs.py
│   ├── 05_build_dataset.py
│   ├── 06_train_model.py
│   ├── 07_validate_model.py
│   ├── 08_export_surrogate.py
│   └── 09_use_in_ga.py
├── data/
│   ├── raw/
│   └── processed/
├── models/
└── reports/
```

---

## Fase 0 — Configuração do problema

> **Condição de saída:** `problem.yaml` completo, um caso manual executado, parsing confirmado, e definição formal do target fechada.

### 0.1 `config/paths.yaml`

```yaml
swan_executable: "/path/to/snl-swan/swan.exe"
swan_template_dir: "/path/to/templates/"
runs_dir: "./data/raw/"
results_dir: "./data/processed/"
models_dir: "./models/"
reports_dir: "./reports/"
```

### 0.2 `config/problem.yaml`

```yaml
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
  mode: "multi_area"   # multi_area | full_domain_mat
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
  random_seed: 42
  split:
    train: 0.70
    val: 0.15
    test: 0.15
```

### 0.3 Definição formal do output

O plano admite dois contratos válidos de output.

**Modo B — `multi_area`:** o surrogate prevê `P_total` e um vector curto `[HRA_area_1, ..., HRA_area_k]`. Cada área é fixa e definida em `problem.yaml`.

**Modo C — `full_domain_mat`:** o surrogate prevê `P_total` e o campo de `Hs` no domínio completo, no mesmo grid de referência escolhido para o treino. O HRA é calculado depois por pós-processamento.

Regra importante: casos históricos sem `.mat` completo podem ser usados no modo B, mas não servem para treinar o modo C.

### 0.4 Caso manual obrigatório

Antes de automatizar qualquer coisa, executar um caso manual completo e guardar:
- input `.swn`
- output de `P_total`
- `.mat` de `Hs`
- script ou função usada para calcular HRA
- log de execução

Sem este caso manual verificado, o pipeline não começa.

---

## Fase 1 — Geração e validação do dataset

> **Condição de saída:** `dataset_v1` congelado, metadados completos, taxa de falha conhecida, e contratos de output respeitados.

### 1.1 Geração dos layouts

**Script:** `src/01_generate_layouts.py`

O gerador cria candidatos para layout e estado de mar, mas só um caso **válido** entra na fila de simulação. Layout inválido é rejeitado antes de qualquer chamada ao SWAN.

#### Regras obrigatórias de layout válido

1. Todos os WECs dentro da área de disposição.
2. Distância mínima entre todos os pares de WECs maior ou igual ao limite definido.
3. Ordenação canónica obrigatória antes de salvar o layout.
4. Nenhum caso duplicado depois da ordenação canónica.

#### Fonte única de verdade

O teu código existente do GA continua a ser a fonte de verdade para a viabilidade geométrica. Um filtro auxiliar pode existir para auditoria, mas não substitui o código principal de produção.

#### Ordenação canónica

A ordenação padrão é por `x` crescente e, em empate, por `y` crescente. O mesmo layout físico nunca deve aparecer com permutações diferentes no dataset.

```python
def canonicalize_layout(layout):
    # layout shape: (N, 2)
    idx = sorted(range(len(layout)), key=lambda i: (layout[i][0], layout[i][1]))
    return layout[idx]
```

### 1.2 Amostragem de estados de mar

Não usar apenas amostragem uniforme cega. O recomendado é importance sampling baseado na scatter diagram real do local, para aumentar a densidade de dados nas regiões de maior ocorrência.

O k-means continua útil como redução operacional dentro de certas optimizações, mas não deve definir o envelope de treino do surrogate.

### 1.3 Cobertura geométrica do dataset

Além de layouts aleatórios, forçar a presença de famílias geométricas específicas:
- grelhas quase regulares
- fileiras alinhadas
- padrões diagonais
- layouts compactos
- layouts dispersos

Isto existe porque o GA tende a gerar estruturas organizadas, e um dataset puramente aleatório pode não cobrir bem essas formas.

### 1.4 Construção dos casos do SWAN

**Script:** `src/02_build_swan_inputs.py`

Cada caso precisa de uma pasta própria, input gerado automaticamente, cópia dos ficheiros fixos, e registo do `case_id`.

### 1.5 Execução batch idempotente

**Script:** `src/03_run_swan_batch.py`

A execução batch deve ser idempotente. Se parar a meio, reinicia e salta os casos já concluídos com sucesso.

Metadados mínimos por caso:
- `case_id`
- `run_status`
- `runtime_sec`
- `error_msg`
- `hash_input`
- caminho dos outputs

### 1.6 Parsing e sanity checks físicos

**Script:** `src/04_parse_outputs.py`

Extrair `P_total`, o `.mat` de `Hs`, e os HRA correspondentes ao contrato do modo escolhido.

Sanity checks obrigatórios antes do caso entrar no dataset:
- `P_total` finito
- `P_total >= 0`
- `Hs` finito nos pontos válidos
- `HRA` finito onde existir área válida
- `HRA <= Hs_entrada` quando o target for média directa de `Hs`

Casos que falham sanity check não entram no dataset de treino. Ficam marcados para auditoria.

### 1.7 Tratamento dos secos

```python
import numpy as np

def clean_hs_field(hs_field):
    hs_field = np.array(hs_field, dtype=float)
    valid = np.isfinite(hs_field) & (hs_field > 0)
    return np.where(valid, hs_field, np.nan)
```

O cálculo do HRA usa só os pontos válidos e a máscara geométrica da área.

### 1.8 Especificação de caso histórico válido

Um caso histórico só entra no treino se tiver, no mínimo:
- layout completo do parque
- número de WECs
- `Hs`, `Tp`, `Dir`
- input original ou estrutura equivalente reconstituível
- `P_total`
- estado de execução conhecido
- identificação do caso

Para modo B, também precisa de:
- HRA calculável para as áreas definidas, ou `.mat` suficiente para recalcular essas áreas

Para modo C, precisa de:
- `.mat` completo do domínio no grid de referência
- informação suficiente para mapear esse campo ao grid correcto

Casos incompletos podem ficar numa pasta de auditoria, mas não entram no treino.

### 1.9 Congelamento do dataset

**Script:** `src/05_build_dataset.py`

Criar e congelar:
- `dataset_v1_scalar.csv` para modo B
- `dataset_v1_field_index.csv` para modo C, com índice para os ficheiros `.mat`

Também guardar:
- estatísticas dos inputs
- estatísticas dos outputs
- percentagem de falha
- distribuição de layouts por família geométrica

---

## Fase 2 — Treino

> **Condição de saída:** baseline treinada, métricas produzidas, e escolha explícita de manter B ou avançar para C.

### 2.1 Split treino/validação/teste

Aplicar a divisão definida no `problem.yaml`. O scaler é ajustado só no treino.

### 2.2 Targets e normalização

`P_total` e HRA entram em unidades físicas no dataset. A normalização min-max para `[0.01, 1]` é aplicada na etapa da fitness function ou em camada explícita de pós-processamento documentada.

Nunca normalizar sem guardar os `xmin` e `xmax` usados. Esses valores fazem parte do contrato do modelo.

```python
def minmax_01(x, xmin, xmax):
    if xmax == xmin:
        return 0.01
    z = (x - xmin) / (xmax - xmin)
    z = max(0.0, min(1.0, z))
    return 0.01 + 0.99 * z
```

### 2.3 Baseline do modo B

Treinar XGBoost para:
- `P_total`
- cada componente de HRA, ou um multi-output leve se for estável

O modo B é a baseline operacional recomendada.

### 2.4 Trilha do modo C

O modo C não é extensão trivial do B. O modo C é previsão de campo e deve ser tratado como trilha separada.

Requisitos mínimos do modo C:
- grid de output fixo e documentado
- estratégia de compressão ou vectorização do campo
- modelo adequado para saída de alta dimensão
- validação espacial, não só escalar

Se o objectivo imediato é substituir o SWAN no GA com o menor risco, fechar primeiro o modo B.

### 2.5 Métricas obrigatórias

Para modo B:
- MAPE global
- RMSE relativo
- R²
- Spearman de ranking
- erro no top 10% dos layouts por desempenho

Para modo C:
- RMSE espacial
- erro no HRA reconstituído
- erro em regiões críticas do domínio
- consistência visual de padrões principais

### 2.6 Gráficos obrigatórios

Guardar em `reports/`:
- predito vs real de `P_total`
- predito vs real de cada HRA
- histograma de erro
- erro por faixa de `Hs`
- erro por faixa de `Tp`
- curva de aprendizagem
- para modo C, mapas de erro espacial

---

## Fase 3 — Validação

> **Condição de saída:** o surrogate é confiável na prática, não apenas em média.

### 3.1 Validação estática

Executar o modelo no conjunto de teste nunca visto.

### 3.2 Validação local

Perturbar layouts reais do teste em escalas pequenas e verificar se a superfície de resposta é suave.

### 3.3 Validação dinâmica

Correr uma optimização curta com o surrogate, depois reavaliar com SNL-SWAN real os melhores indivíduos. Comparar ranking e valores.

### 3.4 Monitorização do topo

Não confiar apenas no erro médio global. Monitorizar explicitamente o erro nos layouts do topo, porque é essa região que o GA mais explora.

### 3.5 Infill opcional

Se as falhas aparecerem concentradas numa região do espaço, gerar novos dados nessa região e retreinar. Esses casos devem entrar em `infill_cases.csv`.

---

## Fase 4 — Interface para o GA

> **Condição de saída:** o GA chama uma função estável, documentada e fisicamente segura.

### 4.1 Contrato da interface

```python
fitness = surrogate.predict_fitness(layout, sea_states, weights, alpha, beta)
```

O GA continua responsável por garantir layout válido antes da chamada.

### 4.2 Validações antes da inferência

Antes de prever:
- confirmar shape correcto do layout
- confirmar N correcto
- confirmar estado de mar dentro do envelope de treino
- confirmar layout ordenado canonicamente

### 4.3 Safety checks de output

Se o surrogate devolver valor impossível, o caso deve ser marcado para auditoria. Não usar clipping silencioso como solução principal. Clipping pode existir como barreira final de segurança, mas deve ser logado sempre.

### 4.4 Fitness normalizada

`P_total` e HRA são transformados para `[0.01, 1]` antes da combinação com `alpha` e `beta`. Os valores de referência da min-max têm de vir do treino congelado, não do lote actual do GA.

### 4.5 Predição vectorizada

Se fores usar muitos estados de mar por indivíduo, prever em batch, não com chamadas uma a uma. Isso reduz muito o overhead.

---

## Fase 5 — Operação e manutenção

> **Condição de saída:** o surrogate continua auditável depois de entrar em produção.

### 5.1 Reavaliação periódica com SWAN real

A cada bloco de gerações, reavaliar um conjunto pequeno dos melhores layouts com o SWAN real e comparar.

### 5.2 Versionamento completo

Cada versão precisa de guardar:
- dataset usado
- contrato do output
- `problem.yaml`
- métricas
- scaler
- parâmetros da min-max
- modelo

### 5.3 Reutilização dos `.mat`

Os `.mat` guardados são activos do projecto. Servem para:
- recalcular HRA com outras áreas
- construir novos datasets sem nova simulação
- migrar de B para C quando quiseres

---

## Checklist por fase

### Fase 0
- [ ] `problem.yaml` revisto
- [ ] caso manual executado
- [ ] parsing confirmado
- [ ] contrato do output definido

### Fase 1
- [ ] layouts válidos respeitam área e espaçamento
- [ ] ordenação canónica aplicada
- [ ] lote piloto aprovado
- [ ] sanity checks físicos implementados
- [ ] casos históricos triados por contrato B ou C
- [ ] `dataset_v1` congelado

### Fase 2
- [ ] baseline B treinada
- [ ] métricas completas geradas
- [ ] erro no top 10% medido
- [ ] decisão explícita sobre avançar ou não para C

### Fase 3
- [ ] validação local aprovada
- [ ] validação dinâmica aprovada
- [ ] monitorização do topo aprovada

### Fase 4
- [ ] interface do GA estabilizada
- [ ] normalização documentada
- [ ] inferência vectorizada testada

### Fase 5
- [ ] versionamento activo
- [ ] reavaliação periódica activa
- [ ] reutilização dos `.mat` documentada

---

## Tripwires

### Tripwire 1 — Geometria
Se aparecer um layout inválido em qualquer etapa depois do gerador, há bug de integração. Parar o pipeline.

### Tripwire 2 — Contrato B/C
Se um caso sem `.mat` completo entrar no treino do modo C, o dataset está contaminado. Parar o pipeline.

### Tripwire 3 — Ordenação
Se o mesmo layout físico surgir com duas codificações diferentes, o dataset está inconsistente. Parar o pipeline.

### Tripwire 4 — Outliers físicos
Se `P_total` negativo, `HRA` não finito, ou `HRA > Hs_entrada` passar para o dataset, há erro de parsing ou de sanidade. Parar o pipeline.

### Tripwire 5 — Erro no topo
Se o surrogate parecer bom em média mas falhar no top 10% dos layouts, não integrar no GA final.

---

## Ligações

- [[Nosso-Mar]]
- [[SNL-SWAN]]
- [[GA Optimização Parques WEC]]
- [[Power Matrix WEC]]
