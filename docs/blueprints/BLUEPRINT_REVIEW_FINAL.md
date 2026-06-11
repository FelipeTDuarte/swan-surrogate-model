---
tags:
  - blueprint
  - review
  - final-review
  - surrogate
  - SWAN
  - GA
aliases:
  - Entrega 13 dos Blueprints
  - Blueprint Review Final
created: 2026-05-16
status: entrega-13
---

# BLUEPRINT_REVIEW_FINAL

> Revisão final da camada de blueprints antes da passagem para implementação.

## Objetivo deste documento

Este ficheiro fecha a fase de blueprints com uma revisão crítica do conjunto já produzido. O objetivo é identificar contradições, lacunas, duplicações, decisões ainda abertas e condições mínimas para passar à implementação sem perder controlo do escopo.

## Resultado geral da revisão

O conjunto atual de blueprints está **coerente** como arquitetura documental. A cadeia completa ficou fechada desde contratos globais até integração no GA, com cobertura explícita para os modos B e C.

O plano auditado foi corretamente propagado para os blueprints. Os pontos que mais importavam para o teu caso ficaram preservados: geometria como restrição inegociável, ordenação canónica, dataset congelado, normalização min-max dentro da fitness, separação B/C, validação do top 10% e rechecagem com SWAN real.

## Verificações estruturais

- plano auditado presente: YES
- blueprints operacionais presentes: YES
- contratos B/C explícitos: YES
- ordenação canónica preservada: YES
- dataset congelado preservado: YES
- validação top 10 por cento preservada: YES
- bounds da fitness preservados na exportação: YES
- fonte de verdade geométrica preservada: YES

## Consistências encontradas

### 1. Linha de contratos estável

A linha `config -> geração -> execução -> parsing -> dataset -> treino -> validação -> exportação -> GA` está bem fechada. Não há salto lógico grande entre etapas.

### 2. B e C deixaram de estar ambíguos

Os blueprints tratam B e C como trilhas relacionadas, mas distintas. Isso corrige uma das zonas mais frágeis dos planos anteriores.

### 3. O GA não perdeu a sua autoridade geométrica

A integração no GA manteve explicitamente o teu código como fonte principal de verdade para layouts válidos. Isso evita a armadilha de “deixar o fitness penalizar depois”.

### 4. O dataset ganhou identidade própria

O treino ficou proibido de refazer merges soltos. Isso melhora rastreabilidade e reduz muito o risco de drift silencioso entre experiências.

### 5. A validação ficou focada no uso real

A presença de top 10%, ranking, sensibilidade local e validação dinâmica é suficiente para impedir uma aprovação ingénua baseada só em erro médio global.

## Contradições encontradas

### Contradição bloqueante

Não encontrei contradição bloqueante entre os blueprints produzidos.

### Tensões menores que ainda exigem atenção na implementação

#### Tensão T1 — split do dataset

O blueprint do dataset deixa aberta a política de split congelado versus split gerado no treino, embora recomende uma opção. Isto não é erro, mas na implementação convém fechar uma decisão única logo no início para evitar duas convenções paralelas.

#### Tensão T2 — formato interno do bundle

O blueprint da exportação fecha o contrato lógico do bundle, mas não fixa um único formato binário. Isso é aceitável nesta fase, mas na implementação deves escolher cedo entre diretório empacotado, pickle controlado ou outro formato explícito.

#### Tensão T3 — arquitetura concreta do modo C

A trilha C está corretamente especificada como problema separado, mas a arquitetura concreta continua em aberto. Isso foi intencional, mas precisa de ser resolvido antes da implementação do treino C.

## Duplicações encontradas

### Duplicação útil

Algumas regras aparecem em mais do que um blueprint, mas isso é duplicação saudável e deliberada. Acontece sobretudo com:
- ordenação canónica
- bounds da fitness
- distinção B/C
- validação geométrica

Estas duplicações são boas porque esses pontos são contratos transversais e precisam de reaparecer onde influenciam comportamento.

### Duplicação a vigiar na implementação

A única duplicação que merece vigilância futura é a existência potencial de um verificador geométrico auxiliar fora do teu código principal. O blueprint já diz que isso só pode existir como auditoria, não como segunda fonte de verdade em produção.

## Lacunas restantes

### Lacuna L1 — schema formal da scatter diagram

A política de amostragem a partir da scatter diagram ficou bem definida, mas o formato exato do ficheiro de entrada ainda não foi fechado como schema formal. Isto não bloqueia o design, mas é um ponto de implementação que convém fechar cedo.

### Lacuna L2 — contrato exato do output energético bruto

Os blueprints dizem corretamente que `P_total` deve ser lido do output declarado no manifesto, mas ainda não congelam o nome final do ficheiro ou o parser exato desse output. Isso precisa ser fechado quando ligares o caso manual real ao código.

### Lacuna L3 — grid de referência do modo C

O modo C exige `grid_id` e `field_shape`, mas ainda falta fechar um identificador concreto do grid de referência e o caminho operacional de armazenamento dos campos já alinhado com o teu caso manual.

## Decisões ainda em aberto

### D1 — política final de split

Escolher entre:
- split gerado no treino e guardado como artefacto
- split já congelado na fase de dataset

A recomendação atual do conjunto é usar split gerado no treino, mas registado e persistido.

### D2 — arquitetura do modo C

Escolher a primeira implementação concreta para previsão de campo:
- regressão sobre campo achatado
- compressão + regressão
- modelo neural espacial dedicado

### D3 — formato binário do bundle exportado

Escolher um formato que seja simples, auditável e estável para o ambiente em que vais correr o GA.

## Gating para passar à implementação

O conjunto está pronto para passar à implementação do **núcleo B**.

Para a trilha B, eu considero que o gating documental está satisfeito. Já existe detalhe suficiente para implementar sem improvisar contratos fundamentais.

Para a trilha C, o gating documental também está quase satisfeito, mas há uma diferença importante: ela ainda precisa de uma decisão de arquitetura concreta antes de começar o código do treino.

## Ordem recomendada de implementação

### Fase I — fechar o caminho B ponta a ponta

1. `problem.yaml` final
2. `01_generate_layouts.py`
3. `02_build_swan_inputs.py`
4. `03_run_swan_batch.py`
5. `04_parse_outputs.py`
6. `05_build_dataset.py`
7. `06_train_model.py` para B
8. `07_validate_model.py` para B
9. `08_export_surrogate.py` para B
10. `09_use_in_ga.py` para B

### Fase II — abrir a trilha C com decisão técnica fechada

1. fechar grid de referência
2. escolher arquitetura do modelo de campo
3. implementar loader de campos e treino C
4. validar C com métricas espaciais e HRA reconstituído

## Juízo final

A camada de blueprints está suficientemente madura para sair da fase de especificação e entrar em implementação controlada.

Se eu fosse resumir numa frase: o sistema já não está “desenhado por intenção”; agora está desenhado por contratos.

## Critérios de aceite desta revisão

Este documento só é considerado fechado se:
- confirmar que não há contradição bloqueante
- listar as tensões menores ainda abertas
- listar lacunas reais e não cosméticas
- indicar gating claro para passar à implementação

## Ligações

- [[surrogate_swan_plano_v2_auditado]]
- [[BLUEPRINTS_INDEX]]
- [[BLUEPRINT_TRACEABILITY]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[BLUEPRINT_09_USE_IN_GA]]
