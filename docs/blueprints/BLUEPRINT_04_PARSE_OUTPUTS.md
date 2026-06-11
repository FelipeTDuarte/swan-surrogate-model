---
tags:
  - blueprint
  - data-pipeline
  - parsing
  - outputs
  - SWAN
  - SNL-SWAN
  - surrogate
aliases:
  - Entrega 6 dos Blueprints
  - Blueprint Parse Outputs
created: 2026-05-16
status: entrega-6
---

# BLUEPRINT_04_PARSE_OUTPUTS

> Especificação operacional do ficheiro responsável por ler os outputs do SNL-SWAN, extrair `P_total`, carregar e limpar o campo de `Hs`, calcular os targets do modo B, indexar os artefactos do modo C e decidir a compatibilidade real de cada caso com o treino.

## Objetivo do ficheiro

Este ficheiro converte resultados brutos de simulação em dados utilizáveis pelo pipeline de treino.

Ele é o ponto onde se decide se um caso que correu realmente gerou informação útil, fisicamente aceitável e compatível com o contrato do modo B, do modo C, ou de ambos. Aqui termina a fase de execução numérica e começa a fase de construção de dados de machine learning.

Este ficheiro não treina modelos, não monta o dataset final congelado e não executa simulações. O seu papel é extrair, validar, limpar e classificar os outputs por caso.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_03_RUN_SWAN_BATCH.md` produz outputs brutos e `run_status.csv`
2. `BLUEPRINT_04_PARSE_OUTPUTS.md` extrai targets e classifica casos
3. `BLUEPRINT_05_BUILD_DATASET.md` monta os datasets congelados B e C

Se este ficheiro falhar, o pipeline pode acabar a treinar com casos incompletos, campos corrompidos ou targets inconsistentes.

## Base externa relevante

A documentação e ferramentas ligadas ao SWAN indicam que o modelo suporta saídas `TABLE` e `BLOCK`, incluindo ficheiros `.mat` para blocos de resultados, e que variáveis como `HSIGN` ou `Hsig` podem ser lidas dessas saídas [web:204][web:283][web:148]. Bibliotecas como `swantools` leem ficheiros block `.mat` e extraem `Hsig`, juntamente com coordenadas e tempos, o que confirma a viabilidade de usar um parser programático robusto [web:148].

Há também um risco conhecido com legibilidade de certos ficheiros `.mat` produzidos por compilações específicas do SWAN, incluindo problemas de endianness ou formato, pelo que o parser deve ser defensivo e registar falhas de leitura sem contaminar o dataset [web:269][web:243].

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `hra.mode`
- `hra.areas`
- `hra.aggregation`
- `storage`

### Input 2 — `config/paths.yaml`

O ficheiro deve usar:
- `runs_dir`
- `processed_dir`
- `logs_dir`
- `archive_dir`

### Input 3 — `data/processed/run_status.csv`

Este ficheiro vem da Entrega 5 e diz que casos terminaram com outputs potencialmente utilizáveis.

Campos mínimos esperados:

```text
case_id, run_status, stdout_file, stderr_file, print_file, output_dir, error_msg
```

### Input 4 — `case_manifest.yaml` por caso

Cada caso deve ter manifesto suficiente para localizar os outputs relevantes e saber o que se esperava guardar.

### Input 5 — outputs brutos do SWAN

Dependendo do teu caso e template, isto pode incluir:
- ficheiro de print do SWAN
- ficheiro ou tabela com `P_total`
- ficheiro `.mat` com campo de `Hs`
- ficheiros auxiliares de output por área, se existirem

## Outputs produzidos

### Output principal 1 — índice parseado por caso

Ficheiro sugerido:

```text
data/processed/parsed_cases.csv
```

Campos mínimos:

```text
case_id, parse_status, run_status, p_total, hs_mat_file, hs_field_valid, valid_for_B, valid_for_C, hra_status, error_msg
```

### Output principal 2 — targets escalares do modo B

Ficheiro sugerido:

```text
data/processed/parsed_targets_B.csv
```

Campos mínimos:

```text
case_id, P_total, HRA_area_1, ..., HRA_area_k
```

### Output principal 3 — índice de campos do modo C

Ficheiro sugerido:

```text
data/processed/parsed_targets_C.csv
```

Campos mínimos:

```text
case_id, P_total, hs_field_file, grid_id, field_shape, valid_for_C
```

### Output auxiliar 1 — relatório de falhas de parsing

Ficheiro sugerido:

```text
reports/parse_failures.csv
```

### Output auxiliar 2 — log do script

Ficheiro sugerido:

```text
reports/logs/04_parse_outputs.log
```

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_run_status_table()`

Carrega e valida `run_status.csv`.

### 2. `select_parseable_cases()`

Escolhe os casos elegíveis para parsing. Em regra, só casos com estado compatível com outputs utilizáveis entram nesta fase.

### 3. `load_case_manifest(case_id)`

Lê o manifesto do caso e encontra os ficheiros esperados.

### 4. `extract_p_total(case_manifest, output_dir)`

Extrai `P_total` do output correspondente.

### 5. `load_hs_field(case_manifest, output_dir)`

Lê o `.mat` ou outro artefacto equivalente e carrega o campo de `Hs`.

### 6. `clean_hs_field(hs_field)`

Aplica limpeza de valores inválidos, secos e não finitos.

### 7. `compute_hra_from_field(hs_field, hra_areas, grid_meta)`

Calcula os HRA das áreas definidas no modo B a partir do campo limpo.

### 8. `assess_case_compatibility(parsed_case)`

Decide se o caso é válido para B, para C, para ambos ou para nenhum.

### 9. `write_parsed_outputs()`

Persiste `parsed_cases.csv`, `parsed_targets_B.csv`, `parsed_targets_C.csv` e o relatório de falhas.

### 10. `update_case_manifest_with_parse_results()`

Atualiza o manifesto do caso com resultados do parsing e compatibilidade.

## Fluxo interno

### Etapa 1 — carregar configs e estado de execução

Ler `problem.yaml`, `paths.yaml` e `run_status.csv`. Selecionar apenas os casos com estado compatível com parsing.

### Etapa 2 — localizar outputs por caso

Usar o manifesto para localizar os ficheiros esperados, em vez de depender apenas de nomes fixos no diretório.

### Etapa 3 — extrair `P_total`

Ler o output apropriado e converter para valor numérico finito.

### Etapa 4 — carregar o campo de `Hs`

Ler o ficheiro `.mat` ou equivalente. Registar falha clara se o ficheiro estiver ausente, ilegível ou estruturalmente incompatível.

### Etapa 5 — limpar o campo

Aplicar máscara a valores não finitos, zeros inválidos e pontos secos conforme a política definida.

### Etapa 6 — calcular HRA para modo B

Aplicar as áreas definidas no problema e a agregação configurada, usando apenas pontos válidos do campo.

### Etapa 7 — classificar compatibilidade B/C

Decidir se o caso é:
- válido para B
- válido para C
- válido para ambos
- inválido para treino

### Etapa 8 — persistir outputs parseados

Guardar tabelas parseadas e atualizar o manifesto.

## Extração de `P_total`

### Objetivo

Transformar o output energético bruto da simulação num escalar único, reprodutível e numericamente confiável.

### Regras

- `P_total` deve ser lido da fonte definida no template e no manifesto do caso
- o parser não deve assumir um nome mágico se o manifesto puder fornecer o caminho
- o valor final deve ser escalar e finito
- `P_total < 0` não entra como caso válido para treino

### Estado de falha

Se `P_total` não puder ser lido ou for não finito, o caso não é válido para B nem para C, salvo se estiveres a preservar artefactos brutos apenas para auditoria.

## Carregamento do campo de `Hs`

### Objetivo

Ler o campo de onda significativo necessário para HRA e para o modo C.

### Fonte esperada

A preferência é usar o `.mat` bruto guardado pelo run, porque este artefacto preserva o campo espacial com maior reutilização futura.

### Regras

- o parser deve suportar pelo menos o formato `.mat` usado na tua cadeia atual
- se o `.mat` falhar na leitura, o caso deve ser marcado com erro explícito
- o parser deve identificar o nome da variável relevante para `Hs`, como `HSIGN` ou `Hsig`, com mapeamento configurável

Ferramentas de terceiros mostram leitura prática de block `.mat` com variáveis do tipo `Hsig`, o que reforça a necessidade de um mapeamento explícito e não de suposições implícitas [web:148][web:279].

### Compatibilidade futura

Se no futuro fores usar outro formato de output, como netCDF, a interface do parser deve permitir novo backend sem mudar o contrato externo.

## Limpeza do campo de `Hs`

### Objetivo

Separar valores físicos utilizáveis de pontos inválidos, secos ou corrompidos.

### Regras mínimas

- manter apenas valores finitos
- converter para `NaN` os pontos considerados inválidos pela política do projeto
- preservar a geometria do campo e da grelha

### Política inicial recomendada

```python
valid = np.isfinite(hs_field) & (hs_field > 0)
hs_clean = np.where(valid, hs_field, np.nan)
```

### Observação importante

Nem todo zero é necessariamente “erro” em qualquer contexto físico, mas na tua cadeia atual a política já assume filtragem de zero, `NA` e positivos válidos. Portanto, o parser deve respeitar essa convenção do projeto, não inventar outra no meio do pipeline [cite:164].

## Cálculo do HRA

### Objetivo

Calcular o valor de HRA para áreas definidas pelo utilizador, a partir do campo limpo de `Hs`.

### Regras

- cada área deve vir de `problem.yaml`
- a máscara espacial deve ser aplicada no mesmo sistema de coordenadas do campo
- a agregação deve seguir o valor configurado, como `mean`
- usar apenas pontos válidos

### Resultado mínimo

Para `k` áreas, produzir:

```text
HRA_area_1, ..., HRA_area_k
```

### Estado de falha

Se uma área não tiver pontos válidos suficientes, o caso não deve ser marcado como válido para B sem registo explícito do problema.

## Compatibilidade com modo B

Um caso é válido para B se, no mínimo:
- `P_total` existir e for finito
- HRA puder ser calculado para todas as áreas exigidas
- os sanity checks físicos forem aprovados

## Compatibilidade com modo C

Um caso é válido para C se, no mínimo:
- `P_total` existir e for finito
- o campo completo de `Hs` estiver disponível no grid de referência
- o campo for legível, limpo e indexável
- a shape do campo for compatível com o contrato do modo C

## Sanity checks físicos

### Verificações mínimas

- `P_total` finito
- `P_total >= 0`
- `Hs` finito nos pontos válidos
- HRA finito nas áreas válidas
- HRA não superior ao `Hs` de entrada quando o target representar média direta do campo de `Hs`

A documentação do SWAN menciona inclusive avisos quando a altura significativa calculada difere de forma relevante da altura imposta em certas condições de fronteira, o que mostra que checks de coerência física e leitura do print file podem ser úteis na cadeia de qualidade [web:281][web:236].

## Tratamento de `.mat` ilegível

### Problema

Há casos conhecidos em que outputs `.mat` do SWAN ficam difíceis de ler por causa de compilação ou endianness [web:269][web:243].

### Regra do parser

Se o `.mat` não puder ser lido:
- marcar `parse_status = MAT_READ_ERROR`
- guardar mensagem de erro
- manter o caso fora do treino
- não tentar “adivinhar” compatibilidade com C

### Política de arquivo

Casos assim podem ser preservados em auditoria, mas não entram no dataset congelado.

## Contrato de `parsed_cases.csv`

### Campos mínimos

```text
case_id, parse_status, run_status, p_total, hs_mat_file, hs_field_valid, valid_for_B, valid_for_C, hra_status, error_msg
```

### Exemplos de `parse_status`

- `OK_B_AND_C`
- `OK_B_ONLY`
- `OK_C_ONLY`
- `P_TOTAL_ERROR`
- `MAT_READ_ERROR`
- `HRA_ERROR`
- `PHYSICS_CHECK_FAILED`
- `MISSING_FILES`

## Contrato de `parsed_targets_B.csv`

### Campos mínimos

```text
case_id, P_total, HRA_area_1, ..., HRA_area_k
```

### Regra

Só casos válidos para B entram aqui.

## Contrato de `parsed_targets_C.csv`

### Campos mínimos

```text
case_id, P_total, hs_field_file, grid_id, field_shape, valid_for_C
```

### Regra

Só casos válidos para C entram aqui.

## Atualização do manifesto

O `case_manifest.yaml` deve receber uma secção de parsing com, no mínimo:

```yaml
parsing:
  parse_status: "OK_B_AND_C"
  p_total: 123.4
  hs_mat_file: "..."
  hs_field_valid: true
  valid_for_B: true
  valid_for_C: true
  hra_values:
    area_1: 0.87
    area_2: 0.64
  error_msg: null
```

## Logging

### Eventos mínimos a registar

- início da fase de parsing
- número de casos elegíveis
- ausência de outputs esperados
- falha na leitura de `P_total`
- falha na leitura de `.mat`
- falha no cálculo de HRA
- reprovação em sanity check físico
- resumo final por tipo de status

## Núcleo comum, modo B e modo C

### Núcleo comum

Ler `P_total`, localizar outputs, carregar e limpar o campo de `Hs`, e atualizar o manifesto é parte comum.

### Diferença para B

No modo B, o objetivo principal é produzir alvos escalares ou vetores curtos. O foco é o cálculo correto do HRA em áreas fixas.

### Diferença para C

No modo C, o objetivo principal é garantir o campo completo como target. O HRA pode até ser derivado depois, mas o campo precisa de sobreviver inteiro e estar indexado com o grid certo.

### Regra prática

Se um caso for válido para C, deve ser aproveitado também para B sempre que as áreas HRA possam ser calculadas.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_03_RUN_SWAN_BATCH.md`
- template e outputs validados no teu caso manual

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- leia `run_status.csv`
- localize outputs por manifesto
- extraia `P_total`
- leia e limpe o campo de `Hs`
- calcule HRA de forma consistente
- decida validade para B e C sem ambiguidade
- produza `parsed_cases.csv`, `parsed_targets_B.csv` e `parsed_targets_C.csv`
- atualize o manifesto por caso

## Riscos e armadilhas

### Armadilha 1

Confiar apenas em nomes fixos de ficheiros e não no manifesto. Isso torna o parser frágil a pequenas mudanças do template.

### Armadilha 2

Misturar “caso corrido” com “caso parseado”. Correr não basta; o output precisa de ser útil e legível.

### Armadilha 3

Tratar qualquer `.mat` legível como válido para C sem verificar shape, grid e completude.

### Armadilha 4

Fazer clipping ou correção silenciosa de valores físicos impossíveis. Isso mascara erro de parsing ou erro numérico.

### Armadilha 5

Calcular HRA sobre pontos inválidos, secos ou fora da máscara espacial correta.

## Checklist de implementação futura

- [ ] carregar `run_status.csv`
- [ ] filtrar casos elegíveis
- [ ] ler manifesto por caso
- [ ] localizar output de `P_total`
- [ ] ler `.mat` de `Hs`
- [ ] tratar falhas de leitura do `.mat`
- [ ] limpar o campo
- [ ] calcular HRA por área
- [ ] aplicar sanity checks físicos
- [ ] decidir validade para B e C
- [ ] escrever `parsed_cases.csv`
- [ ] escrever `parsed_targets_B.csv`
- [ ] escrever `parsed_targets_C.csv`
- [ ] atualizar `case_manifest.yaml`
- [ ] guardar log agregado

## Ligações

- [[BLUEPRINT_03_RUN_SWAN_BATCH]]
- [[BLUEPRINT_05_BUILD_DATASET]]
- [[BLUEPRINT_06_TRAIN_MODEL]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
