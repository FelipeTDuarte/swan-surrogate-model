---
tags:
  - blueprint
  - data-pipeline
  - swan
  - snl-swan
  - inputs
  - surrogate
  - GA
aliases:
  - Entrega 4 dos Blueprints
  - Blueprint Build SWAN Inputs
created: 2026-05-16
status: entrega-4
---

# BLUEPRINT_02_BUILD_SWAN_INPUTS

> Especificação operacional do ficheiro responsável por transformar casos candidatos em diretórios de execução completos do SNL-SWAN, com ficheiros de input, metadados e estrutura reprodutível de run.

## Objetivo do ficheiro

Este ficheiro recebe os casos candidatos já gerados e monta, para cada `case_id`, um diretório pronto para execução do SNL-SWAN.

O seu papel é garantir que cada caso tenha todos os ficheiros necessários, nomes estáveis, metadados consistentes e um `.swn` final coerente com o problema definido em `problem.yaml`.

Este ficheiro não corre o SWAN, não faz parsing dos outputs e não decide se o caso é bom para treino. Ele prepara o terreno para que a execução batch seja previsível e auditável.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_01_GENERATE_LAYOUTS.md` gera `candidates.csv`
2. `BLUEPRINT_02_BUILD_SWAN_INPUTS.md` cria os diretórios e inputs por caso
3. `BLUEPRINT_03_RUN_SWAN_BATCH.md` executa os casos preparados

Se este ficheiro errar em naming, paths, template filling ou cópia de artefactos, os erros podem aparecer só na execução, o que aumenta muito o custo de depuração.

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `geometry`
- `sea_state`
- `hra`
- `storage`

### Input 2 — `config/paths.yaml`

O ficheiro deve usar:
- `swan_executable`
- `swan_template_dir`
- `runs_dir`
- `processed_dir`
- `logs_dir`

### Input 3 — `data/processed/candidates.csv`

O ficheiro deve consumir o output da entrega 3. Cada linha representa um caso candidato pronto para ser convertido em run do SNL-SWAN.

### Input 4 — templates fixos do projeto

O diretório de templates deve conter todos os ficheiros base que não mudam por caso, incluindo o template principal do `.swn` e quaisquer ficheiros auxiliares necessários ao solver.

## Outputs produzidos

### Output principal

Uma árvore de diretórios em `runs_dir`, com um subdiretório por `case_id`.

Formato recomendado:

```text
data/raw/
  CASE_N28_L000137_S000022/
    input/
      INPUT.swn
      static_assets/
      case_manifest.yaml
    output/
    logs/
```

### Output auxiliar 1 — índice dos runs preparados

Ficheiro sugerido:

```text
data/processed/prepared_runs.csv
```

Campos mínimos:

```text
case_id, run_dir, input_swn, manifest_file, prep_status, template_version
```

### Output auxiliar 2 — log do script

Ficheiro sugerido:

```text
reports/logs/02_build_swan_inputs.log
```

## Estrutura obrigatória por caso

Cada caso preparado deve conter, no mínimo:

- pasta `input/`
- pasta `output/`
- pasta `logs/`
- ficheiro `INPUT.swn`
- ficheiro `case_manifest.yaml`

A separação entre `input/` e `output/` é importante porque existem fluxos SWAN que assumem diretório de trabalho com artefactos misturados, e essa divisão ajuda a manter controlo operacional.

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_candidates_table()`

Carrega e valida `candidates.csv`.

### 2. `load_template_assets()`

Descobre e valida os templates base necessários ao caso.

### 3. `build_case_directory(case_id)`

Cria a árvore de pastas do caso de forma idempotente.

### 4. `render_swn_input(case_row, template_context)`

Preenche o template do `.swn` com os parâmetros específicos do caso.

### 5. `build_obstacle_block(layout)`

Transforma o layout dos WECs no bloco ou conjunto de comandos necessário ao `INPUT.swn`.

### 6. `build_sea_state_block(Hs, Tp, Dir)`

Transforma o estado de mar do caso no bloco correspondente do input.

### 7. `copy_static_assets(case_dir)`

Copia ou referencia os ficheiros fixos necessários ao run.

### 8. `write_case_manifest(case_row, case_paths, template_metadata)`

Guarda os metadados do caso preparado.

### 9. `register_prepared_run(case_row, run_info)`

Adiciona o caso ao índice `prepared_runs.csv`.

### 10. `prepare_case(case_row)`

Função orquestradora que monta um run completo para um único caso.

## Fluxo interno

### Etapa 1 — carregar configs e candidatos

Ler `problem.yaml`, `paths.yaml` e `candidates.csv`. Validar schemas antes de criar qualquer run.

### Etapa 2 — validar templates

Confirmar que os ficheiros base existem no diretório de templates e que o template principal do `.swn` está acessível.

### Etapa 3 — preparar diretórios do caso

Criar a árvore de pastas de cada `case_id` de forma idempotente.

### Etapa 4 — construir contexto do template

Reunir, para cada caso:
- layout tabular e matricial
- número de WECs
- estado de mar
- nomes de ficheiros de output esperados
- configuração HRA relevante
- opções de storage

### Etapa 5 — gerar `INPUT.swn`

Renderizar o template principal e escrever o ficheiro final do caso.

### Etapa 6 — copiar assets fixos

Copiar ou ligar os ficheiros estáticos necessários ao run para o diretório apropriado.

### Etapa 7 — escrever manifesto do caso

Gerar `case_manifest.yaml` com os metadados do run preparado.

### Etapa 8 — atualizar índice global

Adicionar o caso preparado a `prepared_runs.csv`.

## Contrato do template `.swn`

O template principal do SNL-SWAN deve ser tratado como artefacto versionado.

### Requisitos do template

O template deve permitir injetar, no mínimo:
- identificador do projeto ou caso
- geometria dos WECs ou obstáculos equivalentes
- estado de mar do caso
- caminhos e nomes dos outputs
- comandos de output necessários para `P_total` e `Hs`

### Regra de versionamento do template

O manifesto de cada caso deve guardar:
- nome do template usado
- hash do template ou versão
- timestamp de preparação

### Observação importante

O SWAN usa ficheiros `.swn` como ficheiros de comando de execução, e os fluxos usuais de run assumem convenções de nome e diretório bem definidas. Por isso, o template não deve ser montado ad hoc em cada script de forma livre [web:232][web:233][web:234].

## Política de construção do `INPUT.swn`

### Blocos conceptuais mínimos

O blueprint não fecha a sintaxe completa linha a linha, mas o `INPUT.swn` final deve ser construído a partir de blocos lógicos estáveis:

1. cabeçalho do projeto/caso
2. domínio e malha
3. batimetria e inputs fixos
4. representação dos WECs/obstáculos
5. estado de mar
6. comandos de cálculo
7. comandos de output
8. `STOP`

A documentação e exemplos de SWAN mostram que o ficheiro de comando organiza entradas e saídas através de comandos próprios, incluindo blocos de output como `BLOCK`, `TABLE` e outros, pelo que esta decomposição por blocos é coerente com a forma natural de configurar runs [web:204][web:217].

### Regra operacional

O script não deve concatenar texto sem controlo. Deve usar placeholders nomeados e uma fase explícita de renderização.

## Representação dos WECs no input

### Objetivo

Converter o layout já validado num conjunto de comandos consistente com a formulação do teu modelo SNL-SWAN.

### Regras

- a ordem dos WECs no `.swn` deve seguir a ordenação canónica do layout
- o número de entidades escritas no `.swn` deve coincidir com `n_wecs`
- todas as coordenadas devem ser escritas em metros no sistema local definido
- qualquer parâmetro fixo por WEC deve vir de configuração ou template, nunca hardcoded no meio do loop

### Fonte de verdade

A forma exata de escrever os WECs no `.swn` deve seguir o padrão já validado no teu caso manual e no template base do projeto. Este blueprint só fecha as regras de montagem e rastreabilidade.

## Representação do estado de mar no input

### Objetivo

Escrever no `INPUT.swn` o estado de mar específico do caso.

### Regras

- usar a tripla `Hs`, `Tp`, `Dir` exatamente na ordem do contrato global
- manter unidades físicas consistentes
- não permitir que valores fora do envelope entrem no ficheiro final sem `WARNING`

A gramática de entrada do SWAN inclui opções para especificar condições e outputs através de comandos de ficheiro e parâmetros próprios, pelo que a geração programática do input deve respeitar uma estrutura determinística e não livre [web:204][web:240].

## Artefactos estáticos

### O que pode ser tratado como estático

Dependendo do teu caso, podem ser estáticos:
- bathymetry files
- power matrix files
- ficheiros auxiliares fixos
- assets do template
- scripts de inicialização do run

### Regra

Um asset estático só pode ser tratado como tal se for igual para todos os casos daquele surrogate.

Se variar por caso, deve ser gerado ou parametrizado, não copiado cegamente.

## Política de cópia versus referência

### Opção preferida

Copiar para o diretório do caso os ficheiros mínimos necessários à reprodutibilidade local do run.

### Justificação

Estruturas de runs SWAN em lote frequentemente organizam um diretório por corrida, contendo input, output e scripts associados. Isso reduz dependências externas implícitas e facilita relançamento de um caso isolado [web:141][web:235].

### Regra prática

Se um ficheiro for grande demais para copiar para todos os casos, o manifesto deve indicar claramente que ele é referenciado por caminho compartilhado.

## Contrato do `case_manifest.yaml`

Cada run preparado deve ter um manifesto com, no mínimo:

```yaml
case_id: "CASE_N28_L000137_S000022"
problem_id: "swan_surrogate_n28_v1"
layout_id: "LAY_N28_grid_000143"
sea_state_id: "SEA_000022"
run_dir: "data/raw/CASE_N28_L000137_S000022"
input_swn: "data/raw/CASE_N28_L000137_S000022/input/INPUT.swn"
template_name: "base_case_template.swn.j2"
template_version: "v1"
layout_ordering: "sort_by_x_then_y"
n_wecs: 28
sea_state:
  Hs: 1.8
  Tp: 9.5
  Dir: 260.0
storage:
  save_full_mat: true
  save_area_mats: true
expected_outputs:
  p_total_file: "..."
  hs_mat_file: "..."
prep_status: "READY"
```

### Regra

O manifesto deve ser suficiente para reconstituir o caso preparado sem ter de reabrir `candidates.csv`.

## Idempotência

A preparação dos runs deve ser idempotente.

### Regra operacional

Se um caso já existir e os hashes dos inputs forem compatíveis, o script deve poder:
- saltar o caso
- ou reescrever de forma controlada se `force_overwrite = true`

### Regra de segurança

Nunca sobrescrever silenciosamente um `INPUT.swn` já existente sem log e sem critério explícito.

## Validações obrigatórias

### Validações antes da criação do caso

- `case_id` presente e único
- número de colunas do layout coerente com `n_wecs`
- `Hs`, `Tp`, `Dir` finitos
- template principal existente
- assets fixos acessíveis

### Validações do `.swn` renderizado

- nenhum placeholder por preencher
- número de WECs escrito coerente com `n_wecs`
- nomes de outputs definidos
- ficheiro não vazio
- comando final de encerramento presente

### Validações do diretório do caso

- pastas `input/`, `output/` e `logs/` existem
- `INPUT.swn` existe
- `case_manifest.yaml` existe
- índice `prepared_runs.csv` atualizado

## Logging

### Eventos mínimos a registar

- início do script
- número de candidatos carregados
- template usado
- caso preparado com sucesso
- caso ignorado por já existir
- erro de renderização
- erro de cópia de assets
- inconsistência entre layout e `n_wecs`

## Núcleo comum, modo B e modo C

### Núcleo comum

A preparação do input do SWAN é quase totalmente comum aos modos B e C, porque ambos precisam do mesmo run físico base.

### Diferença para B

No modo B, os outputs exigidos podem ser mínimos, desde que permitam obter `P_total` e HRA nas áreas definidas.

### Diferença para C

No modo C, o `INPUT.swn` e a estratégia de output têm de garantir armazenamento do campo de `Hs` no domínio completo, porque esse campo é parte do target futuro.

### Regra prática

Sempre que possível, preparar os runs já com outputs suficientemente ricos para reutilização futura, mesmo que o treino inicial comece em B.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_01_GENERATE_LAYOUTS.md`
- template base do teu caso manual validado

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- leia `candidates.csv`
- crie um diretório reproduzível por `case_id`
- gere `INPUT.swn` sem placeholders soltos
- registe manifesto e índice global
- suporte rerun idempotente
- prepare artefactos suficientes para a execução batch seguinte

## Riscos e armadilhas

### Armadilha 1

Espalhar a lógica do `.swn` por vários pontos do código. Isso torna difícil auditar diferenças entre casos.

### Armadilha 2

Misturar ficheiros estáticos e gerados sem manifesto. Depois fica difícil saber o que veio do template e o que foi criado por caso.

### Armadilha 3

Assumir que o nome do ficheiro de input pode variar livremente. Os fluxos de execução SWAN costumam seguir convenções explícitas para o ficheiro `.swn` e o diretório de trabalho [web:232][web:233].

### Armadilha 4

Gerar apenas o mínimo necessário para B e perder a oportunidade de guardar artefactos úteis para C.

### Armadilha 5

Não versionar o template do `.swn`. Quando houver diferença de resultados, fica quase impossível saber se veio do layout, do estado de mar ou do template.

## Checklist de implementação futura

- [ ] carregar `candidates.csv`
- [ ] validar templates
- [ ] criar árvore de diretórios por caso
- [ ] montar contexto do template
- [ ] renderizar `INPUT.swn`
- [ ] copiar assets fixos
- [ ] escrever `case_manifest.yaml`
- [ ] atualizar `prepared_runs.csv`
- [ ] garantir idempotência
- [ ] guardar logs

## Ligações

- [[BLUEPRINT_01_GENERATE_LAYOUTS]]
- [[BLUEPRINT_03_RUN_SWAN_BATCH]]
- [[BLUEPRINT_04_PARSE_OUTPUTS]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
