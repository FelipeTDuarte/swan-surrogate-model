---
tags:
  - blueprint
  - data-pipeline
  - swan
  - snl-swan
  - batch
  - execution
  - surrogate
  - GA
aliases:
  - Entrega 5 dos Blueprints
  - Blueprint Run SWAN Batch
created: 2026-05-16
status: entrega-5
---

# BLUEPRINT_03_RUN_SWAN_BATCH

> Especificação operacional do ficheiro responsável por executar em lote os casos já preparados do SNL-SWAN, com controlo de estado, retoma segura, logs por caso e rastreabilidade completa de sucesso ou falha.

## Objetivo do ficheiro

Este ficheiro recebe os runs já preparados e executa o SNL-SWAN de forma controlada. O objetivo não é interpretar resultados nem decidir se um caso serve para treino. O objetivo é lançar as simulações, recolher sinais de sucesso ou falha e deixar cada caso num estado inequívoco.

Este é o ponto do pipeline onde erros de infraestrutura, caminhos, permissões, template inválido, timeout ou crash do solver aparecem com mais frequência. Por isso, o ficheiro deve ser pensado como um executor robusto e auditável, não como um simples loop de chamadas ao executável.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` prepara diretórios e `INPUT.swn`
2. `BLUEPRINT_03_RUN_SWAN_BATCH.md` executa os casos preparados
3. `BLUEPRINT_04_PARSE_OUTPUTS.md` lê outputs e faz sanity checks

Se este ficheiro falhar em gestão de estado, o parsing seguinte pode confundir caso não corrido com caso corrido sem output.

## Base operacional externa

A documentação de execução do SWAN descreve o uso de `swanrun` ou `swanrun.bat`, chamando o input sem a extensão `.swn`, e indica modos de execução série, OpenMP e MPI consoante a plataforma e a instalação [web:232][web:233][web:264]. Também há fluxos SNL-SWAN que usam um diretório de input com um ficheiro como `INPUT.swn`, o que encaixa bem na estrutura por caso já definida nas entregas anteriores [web:234][web:260][web:267].

Isto significa que o blueprint não deve assumir uma única forma rígida de lançamento, mas deve suportar pelo menos uma estratégia principal e uma estratégia alternativa. A estratégia principal recomendada é usar o wrapper de run da instalação quando ele existir. A alternativa é executar o binário direto, se a tua instalação e o teu caso manual já provarem isso como válido [web:232][web:233][web:258].

## Inputs esperados

### Input 1 — `config/paths.yaml`

O ficheiro deve ler, no mínimo:
- `swan_executable`
- `runs_dir`
- `processed_dir`
- `logs_dir`

### Input 2 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- opções de execução que venham a ser adicionadas ao contrato global

### Input 3 — `data/processed/prepared_runs.csv`

Este ficheiro vem da Entrega 4 e define que casos estão preparados para execução.

Campos mínimos esperados:

```text
case_id, run_dir, input_swn, manifest_file, prep_status, template_version
```

### Input 4 — diretórios de run por caso

Cada `case_id` deve já existir em `runs_dir` com a árvore mínima esperada:
- `input/`
- `output/`
- `logs/`
- `INPUT.swn`
- `case_manifest.yaml`

## Outputs produzidos

### Output principal — estado de execução por caso

Ficheiro sugerido:

```text
data/processed/run_status.csv
```

Campos mínimos:

```text
case_id, run_status, launch_mode, n_procs, started_at, finished_at, runtime_sec, return_code, timeout_hit, stdout_file, stderr_file, print_file, output_dir, error_msg
```

### Output auxiliar 1 — logs agregados do executor

Ficheiro sugerido:

```text
reports/logs/03_run_swan_batch.log
```

### Output auxiliar 2 — logs por caso

Cada caso deve ter pelo menos:

```text
data/raw/CASE_.../logs/stdout.log
data/raw/CASE_.../logs/stderr.log
```

### Output auxiliar 3 — atualização do manifesto

O `case_manifest.yaml` deve ser atualizado com o estado da execução e os caminhos dos ficheiros gerados.

## Estados permitidos de execução

O pipeline deve usar um conjunto finito e explícito de estados.

### Estados mínimos

- `READY`
- `RUNNING`
- `OK`
- `FAILED`
- `TIMEOUT`
- `MISSING_OUTPUTS`
- `SKIPPED_ALREADY_OK`

### Regra

Um caso nunca deve ficar em estado ambíguo, como “talvez correu”. O executor deve sempre decidir um estado final e persistir essa decisão.

## Estratégias de lançamento suportadas

### Estratégia A — wrapper `swanrun` / `swanrun.bat`

A documentação do SWAN descreve a chamada do wrapper de run com o nome do input sem extensão, tanto em Windows como em Unix/Linux, incluindo opções de paralelização via OpenMP ou MPI [web:232][web:233][web:264].

Esta deve ser a estratégia preferida quando a instalação local segue a convenção padrão do SWAN e quando o teu caso manual já a confirmou.

Exemplos conceptuais:

```text
Windows: swanrun INPUT [nprocs]
Linux:   ./swanrun -input INPUT [-omp n | -mpi n]
```

### Estratégia B — binário direto

Em algumas instalações e tutoriais, o run pode ser feito a partir do executável em conjunto com o ficheiro de comando preparado no diretório de trabalho [web:258][web:234].

Esta estratégia só deve ser usada se o teu ambiente já estiver validado com ela. Não deve ser a via implícita por omissão sem prova prática.

## Política de diretório de trabalho

O executor deve correr cada caso com `cwd` definido para o diretório do próprio caso, ou para o subdiretório operacional definido de forma consistente.

Isto é importante porque os fluxos clássicos de SWAN assumem que o ficheiro de input e os outputs vivem no diretório do modelo, e vários procedimentos de run partem dessa convenção [web:233][web:259].

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_prepared_runs()`

Carrega e valida `prepared_runs.csv`.

### 2. `resolve_launch_strategy()`

Decide se o caso será lançado por wrapper `swanrun` ou por binário direto.

### 3. `build_run_command(case_row, strategy)`

Constrói a linha de comando final a executar.

### 4. `is_case_already_done(case_row)`

Verifica se o caso já foi concluído com sucesso e se os outputs mínimos existem.

### 5. `mark_case_running(case_id)`

Atualiza o estado antes de lançar o processo.

### 6. `run_case(case_row)`

Executa um caso único, com captura de stdout, stderr, timing e código de retorno.

### 7. `detect_expected_outputs(case_row)`

Confirma a presença dos outputs mínimos após a execução.

### 8. `finalize_case_status(case_id, run_result)`

Decide e grava o estado final do caso.

### 9. `update_case_manifest(case_id, run_result)`

Atualiza o manifesto local com dados da execução.

### 10. `run_batch()`

Orquestra a execução do lote completo.

## Fluxo interno

### Etapa 1 — carregar configs e runs preparados

Ler `paths.yaml`, `problem.yaml` e `prepared_runs.csv`. Validar schemas e detectar o modo de lançamento disponível.

### Etapa 2 — filtrar casos elegíveis

Selecionar apenas casos com `prep_status` compatível com execução e excluir os que já estejam `OK`, a menos que o utilizador force rerun.

### Etapa 3 — validar diretórios e inputs

Antes de lançar o processo, confirmar que o diretório do caso existe e que `INPUT.swn` está presente.

### Etapa 4 — lançar o processo

Executar o comando correspondente, redirecionar `stdout` e `stderr`, medir tempo de execução e aplicar timeout.

### Etapa 5 — inspecionar outputs mínimos

Após o término, verificar se os ficheiros de saída mínimos esperados existem. Se o processo devolver sucesso mas os outputs mínimos faltarem, o caso não deve ser marcado como `OK`.

### Etapa 6 — persistir estado final

Gravar `run_status.csv`, atualizar o manifesto e emitir logs agregados.

## Idempotência e retoma

### Objetivo

O executor deve conseguir ser interrompido e retomado sem perder o controlo do lote.

### Regra operacional

Se um caso já tiver estado `OK` e os outputs mínimos estiverem presentes, o script deve marcá-lo como `SKIPPED_ALREADY_OK` ou simplesmente não o voltar a correr, conforme a política escolhida.

### Regra de retoma

Se o processo parar a meio, uma nova execução deve usar `run_status.csv` e o manifesto para saber o que já foi concluído e o que ainda está pendente.

### Regra de segurança

Casos em estado `RUNNING` encontrados numa nova sessão devem ser reavaliados. O script não deve assumir automaticamente que terminaram bem.

## Política de paralelização

### Nível 1 — paralelização interna do SWAN

A documentação do SWAN distingue execução série, OpenMP e MPI através do wrapper de run e do número de processos especificado [web:233][web:264].

### Nível 2 — paralelização externa do lote

Além da paralelização interna de um caso, o executor pode lançar vários casos em paralelo, desde que haja isolamento suficiente de diretórios e recursos.

### Regra principal

Não misturar agressivamente paralelização externa com paralelização interna sem controlo de recursos. O blueprint deve prever uma política clara de `max_concurrent_cases` e `n_procs_per_case`.

### Recomendação prática

Começar com poucos casos em paralelo e `n_procs_per_case` conservador, validando estabilidade antes de escalar.

## Política de timeout

Cada caso deve ter timeout configurável.

### Regra

Se o processo ultrapassar o tempo máximo, o executor deve:
1. terminar o processo
2. marcar `TIMEOUT`
3. guardar logs
4. não tentar fazer parsing como se o caso tivesse terminado bem

## Deteção de sucesso

Sucesso não deve ser decidido apenas por `return_code == 0`.

### Critérios mínimos de `OK`

- processo terminou sem timeout
- código de retorno compatível com sucesso
- outputs mínimos esperados existem
- logs não indicam falha crítica conhecida, se esse parser simples estiver disponível

### Critérios de `MISSING_OUTPUTS`

- processo termina, mas faltam outputs mínimos
- ou os outputs existem, mas estão vazios quando isso for claramente inválido

## Outputs mínimos esperados

O conjunto exato pode variar com o teu template e a tua instalação, mas o blueprint exige que cada caso defina no manifesto os outputs mínimos que provam execução útil.

### Mínimos recomendados

- ficheiro principal de print ou log do SWAN
- output necessário para `P_total`
- output necessário para `Hs`

A gramática e os modos de output do SWAN incluem várias formas de escrita de resultados, pelo que a deteção deve ser baseada no contrato do teu caso preparado e não num nome mágico hardcoded [web:236][web:240].

## Contrato de `run_status.csv`

### Linha mínima por caso

```text
case_id, run_status, launch_mode, n_procs, started_at, finished_at, runtime_sec, return_code, timeout_hit, stdout_file, stderr_file, print_file, output_dir, error_msg
```

### Regras

- deve existir uma linha por caso tentado ou decidido
- o último estado persistido deve refletir a situação final conhecida
- `error_msg` não deve ser vazio quando o estado for `FAILED` ou `TIMEOUT`, salvo impossibilidade real

## Atualização do `case_manifest.yaml`

Depois da execução, o manifesto do caso deve conter, além do que já existia:

```yaml
execution:
  launch_mode: "swanrun"
  n_procs: 1
  started_at: "..."
  finished_at: "..."
  runtime_sec: 42.7
  return_code: 0
  timeout_hit: false
  run_status: "OK"
  stdout_file: "..."
  stderr_file: "..."
  print_file: "..."
```

## Logging

### Eventos mínimos a registar

- arranque do lote
- número de casos elegíveis
- estratégia de lançamento escolhida
- início e fim de cada caso
- timeout
- falha de comando
- outputs em falta
- resumo final do lote

### Regra

Os logs devem permitir responder a três perguntas sem abrir o código:
1. que caso correu
2. como foi lançado
3. porque terminou no estado em que terminou

## Núcleo comum, modo B e modo C

### Núcleo comum

A execução batch do SNL-SWAN é praticamente igual para B e C. O solver físico corrido é o mesmo.

### Diferença para B

No modo B, o conjunto mínimo de outputs necessários pode ser menor, desde que permita obter `P_total` e os HRA definidos.

### Diferença para C

No modo C, a execução deve garantir que o campo completo necessário ao target é efetivamente escrito e guardado. Um caso que corra “bem” mas sem esse campo não é útil para C.

### Regra prática

Se o custo de armazenamento for aceitável, vale mais preparar a execução com outputs ricos o suficiente para C e depois reaproveitar para B, do que descobrir tarde que faltam artefactos.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_02_BUILD_SWAN_INPUTS.md`
- convenção de execução validada no teu caso manual

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- leia `prepared_runs.csv`
- lance os casos com uma estratégia explícita
- capture stdout e stderr
- controle timeout
- distinga `OK`, `FAILED`, `TIMEOUT` e `MISSING_OUTPUTS`
- retome um lote interrompido sem perder rastreabilidade
- produza `run_status.csv` e atualize o manifesto por caso

## Riscos e armadilhas

### Armadilha 1

Assumir que `return_code == 0` basta para declarar sucesso. Em modelos batch, isso muitas vezes mascara casos sem outputs úteis.

### Armadilha 2

Não separar diretórios por caso. Isso torna difícil relançar casos específicos e pode misturar artefactos.

### Armadilha 3

Misturar paralelização do lote com paralelização interna do SWAN sem controlo. Isso pode saturar recursos e piorar estabilidade.

### Armadilha 4

Não tratar o estado `RUNNING` deixado por uma sessão interrompida. Esse é um clássico gerador de ambiguidade operacional.

### Armadilha 5

Amarrar a deteção de sucesso a nomes fixos demais. Os outputs do SWAN dependem da configuração do comando de output, logo o contrato deve vir do manifesto do caso [web:236][web:240].

## Checklist de implementação futura

- [ ] carregar `prepared_runs.csv`
- [ ] resolver estratégia de lançamento
- [ ] validar diretório e `INPUT.swn` por caso
- [ ] lançar processo com `cwd` controlado
- [ ] capturar stdout e stderr
- [ ] medir tempo de execução
- [ ] aplicar timeout
- [ ] verificar outputs mínimos
- [ ] persistir `run_status.csv`
- [ ] atualizar `case_manifest.yaml`
- [ ] suportar retoma do lote
- [ ] guardar log agregado

## Ligações

- [[BLUEPRINT_02_BUILD_SWAN_INPUTS]]
- [[BLUEPRINT_04_PARSE_OUTPUTS]]
- [[BLUEPRINT_05_BUILD_DATASET]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
