---
tags:
  - blueprint
  - validation
  - surrogate
  - SWAN
  - GA
  - machine-learning
aliases:
  - Entrega 9 dos Blueprints
  - Blueprint Validate Model
created: 2026-05-16
status: entrega-9
---

# BLUEPRINT_07_VALIDATE_MODEL

> Especificação operacional do ficheiro responsável por validar o surrogate de forma rigorosa antes da sua exportação e integração no GA, com foco em erro prático, estabilidade local, ranking e comportamento na região de maior interesse do otimizador.

## Objetivo do ficheiro

Este ficheiro verifica se o modelo treinado é realmente utilizável no problema de optimização. O foco não é só medir erro médio. O foco é descobrir se o surrogate mantém ranking útil, responde de forma estável a pequenas perturbações de layout e continua confiável quando o GA explora os melhores indivíduos.

Este ficheiro não treina modelos novos, não reconstrói datasets e não volta à fase de parsing bruto. Ele recebe modelos treinados, bundles, splits e datasets congelados, e produz um juízo técnico sobre se o surrogate pode ou não avançar para exportação e uso operacional.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_06_TRAIN_MODEL.md` produz modelos e bundles treinados
2. `BLUEPRINT_07_VALIDATE_MODEL.md` valida os modelos fora do treino
3. `BLUEPRINT_08_EXPORT_SURROGATE.md` só deve exportar modelos aprovados

Se esta etapa for fraca, o pipeline pode aprovar um surrogate bonito em média e inútil exatamente no topo da paisagem de fitness.

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `training.split`
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

### Input 3 — datasets congelados

O ficheiro deve usar os mesmos datasets congelados que alimentaram o treino:

```text
data/processed/dataset_B_vX.csv
data/processed/dataset_C_index_vX.csv
```

### Input 4 — artefactos do treino

O ficheiro deve consumir, no mínimo:
- bundles dos modelos treinados
- scalers
- splits por `case_id`
- `train_registry.yaml`
- métricas produzidas no treino

### Input 5 — acesso opcional ao SNL-SWAN real

Para a validação dinâmica, o ficheiro pode precisar de chamar a cadeia real de simulação para reavaliar layouts escolhidos pelo surrogate.

## Outputs produzidos

### Outputs principais

1. `reports/validation_report.md`
2. `reports/validation_metrics_B.yaml`
3. `reports/validation_metrics_C.yaml`
4. `reports/validation_decision.yaml`
5. `reports/logs/07_validate_model.log`

### Outputs auxiliares recomendados

1. `reports/validation_topk.csv`
2. `reports/validation_local_sensitivity.csv`
3. `reports/validation_dynamic_recheck.csv`
4. `reports/validation_plots/`

## Função de cada output auxiliar

### `validation_topk.csv`

Regista o comportamento do surrogate nos melhores layouts segundo o próprio surrogate e segundo a reavaliação de referência.

### `validation_local_sensitivity.csv`

Guarda perturbações locais de layout e resposta correspondente do surrogate e da referência.

### `validation_dynamic_recheck.csv`

Guarda a comparação entre avaliações do surrogate e reavaliações reais do SWAN para layouts selecionados.

### `validation_decision.yaml`

Regista a decisão final de aprovação, reprovação ou aprovação condicionada.

## Regra central do ficheiro

O surrogate não pode ser aprovado com base apenas em métricas médias globais. A validação deve incluir ranking, top 10%, sensibilidade local e, sempre que viável, reavaliação dinâmica com o solver real.

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_model_bundle(mode)`

Carrega o bundle do modelo treinado e valida o contrato do artefacto.

### 2. `load_validation_split(mode)`

Carrega os `case_id` correspondentes ao split de teste ou validação final.

### 3. `predict_on_holdout(mode)`

Executa o surrogate no conjunto nunca visto da etapa de validação.

### 4. `compute_validation_metrics(mode)`

Calcula métricas globais e específicas por modo.

### 5. `evaluate_top_region(mode)`

Mede erro e ranking na região de melhor desempenho.

### 6. `run_local_sensitivity_checks(mode)`

Perturba layouts selecionados e mede estabilidade local da resposta.

### 7. `run_dynamic_recheck(mode)`

Escolhe layouts relevantes e compara surrogate com SNL-SWAN real.

### 8. `make_validation_plots(mode)`

Gera gráficos e mapas obrigatórios.

### 9. `decide_model_readiness(mode)`

Decide se o modelo pode seguir para exportação.

### 10. `write_validation_outputs()`

Persiste relatórios, métricas, tabelas e decisão final.

## Fluxo interno

### Etapa 1 — carregar bundles, splits e datasets

Ler os artefactos do treino e confirmar que os datasets e splits usados na validação correspondem às versões certas.

### Etapa 2 — validação estática em holdout

Executar o surrogate no conjunto nunca visto e calcular métricas globais.

### Etapa 3 — análise da região de topo

Avaliar explicitamente os casos do top 10% e, se útil, top 5% por desempenho.

### Etapa 4 — sensibilidade local

Aplicar pequenas perturbações a layouts reais e observar continuidade e estabilidade da resposta.

### Etapa 5 — validação dinâmica

Rodar uma optimização curta com o surrogate ou selecionar layouts candidatos e reavaliar com SNL-SWAN real.

### Etapa 6 — decisão

Gerar uma decisão explícita de aprovação, reprovação ou aprovação com restrições.

## Validação estática

### Objetivo

Responder à pergunta básica: fora do treino, o modelo ainda prevê com erro aceitável?

### Regras

- usar apenas conjunto nunca visto
- não recalibrar scalers nem hiperparâmetros durante a validação
- reportar métricas por target e agregadas

### Métricas mínimas do modo B

- RMSE
- MAE
- R²
- Spearman
- MAPE, se adequado

### Métricas mínimas do modo C

- RMSE espacial
- MAE espacial
- erro no `P_total`
- erro no HRA reconstituído

## Validação da região de topo

### Objetivo

Responder à pergunta prática: o surrogate é bom onde o GA mais vai explorar?

### Regras

- ordenar layouts por desempenho real e por desempenho predito
- medir sobreposição entre conjuntos de topo
- medir erro absoluto e relativo no top 10%
- avaliar consistência do ranking local

### Saídas mínimas

- tabela com `case_id`, valor real, valor predito e posição no ranking
- métrica de Spearman na região de topo
- erro médio e erro máximo no top 10%

## Sensibilidade local

### Objetivo

Verificar se pequenas variações de layout geram resposta suave e coerente, em vez de saltos artificiais do modelo.

### Estratégia mínima

1. escolher layouts reais relevantes
2. aplicar pequenas perturbações admissíveis nas coordenadas
3. manter geometria válida
4. comparar resposta do surrogate e da referência, quando viável

### Regra importante

A perturbação nunca deve criar layouts inválidos. O mesmo filtro geométrico do projeto continua a valer aqui.

### Saídas mínimas

- variação do target por perturbação
- gradiente empírico local aproximado
- sinalização de descontinuidades suspeitas

## Validação dinâmica

### Objetivo

Verificar se o surrogate funciona dentro do ciclo de decisão real da optimização, não só em amostras estáticas.

### Estratégia mínima recomendada

1. correr uma optimização curta com o surrogate
2. recolher os melhores layouts encontrados
3. reavaliar esses layouts com SNL-SWAN real
4. comparar fitness, ranking e erro por componente

### Estratégia alternativa

Se ainda não quiseres ligar um GA curto, selecionar um conjunto de layouts promissores pelo surrogate e reavaliá-los diretamente com o solver real.

### Regra

A validação dinâmica é a etapa mais importante antes de pôr o surrogate no GA final.

## Métricas obrigatórias do modo B

### Globais

- RMSE
- MAE
- R²
- Spearman
- erro por faixa de `Hs`
- erro por faixa de `Tp`
- erro por família geométrica

### Região de topo

- erro médio no top 10%
- erro máximo no top 10%
- Spearman no top 10%
- taxa de interseção entre top real e top predito

### Dinâmicas

- erro de fitness nos melhores layouts reavaliados
- erro de ranking entre layouts reavaliados

## Métricas obrigatórias do modo C

### Globais

- RMSE espacial do campo
- MAE espacial do campo
- erro no `P_total`
- erro do HRA reconstituído por área

### Estruturais

- consistência visual do padrão espacial
- erro em regiões críticas do domínio
- estabilidade do campo sob pequenas perturbações plausíveis

### Dinâmicas

- diferença no HRA reconstituído após reavaliação real
- impacto na fitness quando o campo é usado a jusante

## Critérios mínimos de aprovação do modo B

O modelo B só pode ser aprovado se:
- mantiver ranking útil no holdout
- não colapsar no top 10%
- apresentar resposta local estável
- passar pela validação dinâmica com erro prático aceitável

### Critérios de reprovação imediata

- ranking inconsistente
- erro elevado nos melhores layouts
- saltos não físicos em sensibilidade local
- divergência forte entre surrogate e SWAN nos layouts escolhidos pelo próprio surrogate

## Critérios mínimos de aprovação do modo C

O modelo C só pode ser aprovado se:
- reconstruir o campo com estrutura útil
- permitir HRA reconstituído com erro aceitável
- não perder coerência espacial nas regiões críticas
- sobreviver à validação dinâmica em layouts relevantes

### Critérios de reprovação imediata

- campos espacialmente incoerentes
- HRA derivado instável
- custo muito alto sem ganho operacional claro
- inconsistência grande entre campo previsto e campo real em zonas relevantes

## Política de decisão

### Estados finais possíveis

- `APPROVED`
- `APPROVED_WITH_RESTRICTIONS`
- `REJECTED`

### Exemplos de restrições possíveis

- aprovado só para modo B
- aprovado só dentro de certo envelope operacional
- aprovado para estudos exploratórios, mas não para GA final

### Regra

A decisão final deve ser explícita e acompanhada de razões objetivas.

## Contrato de `validation_decision.yaml`

Este ficheiro deve guardar, no mínimo:

```yaml
validation_run_id: "val_B_v1"
problem_id: "swan_surrogate_n28_v1"
dataset_version: "v1"
mode: "B"
decision: "APPROVED"
reasons:
  - "ranking_stable"
  - "top10_error_acceptable"
  - "dynamic_recheck_passed"
restrictions: []
created_at: "..."
```

## Gráficos obrigatórios

### Modo B

Guardar em `reports/validation_plots/`:
- predito vs real
- histograma de erro
- erro por `Hs`
- erro por `Tp`
- erro por família geométrica
- ranking top 10%

### Modo C

Guardar também:
- mapas de erro espacial
- comparação visual campo real vs predito
- erro do HRA reconstituído por área

### Dinâmica

Guardar ainda:
- surrogate vs SWAN real para layouts reavaliados
- comparação da fitness final

## Logging

### Eventos mínimos a registar

- bundles carregados
- datasets e splits confirmados
- início e fim da validação estática
- início e fim da análise de topo
- início e fim da sensibilidade local
- início e fim da validação dinâmica
- decisão final por modo

## Núcleo comum, modo B e modo C

### Núcleo comum

Holdout, rastreabilidade de artefactos, análise da região de topo, decisão final e logging pertencem ao núcleo comum.

### Diferença para B

O modo B valida principalmente targets escalares ou vetores curtos e o seu impacto direto na fitness.

### Diferença para C

O modo C exige validação espacial e verificação do HRA reconstituído a partir do campo.

### Regra prática

Mesmo quando B e C forem avaliados no mesmo script, a decisão de aprovação deve ser emitida separadamente por modo.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_06_TRAIN_MODEL.md`
- modelos treinados, bundles e splits reproduzíveis

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- valide modelos em holdout sem recontaminar treino
- meça desempenho no top 10%
- execute checks de sensibilidade local
- suporte reavaliação dinâmica com SWAN real
- produza uma decisão final explícita por modo
- gere relatórios, métricas e tabelas de suporte

## Riscos e armadilhas

### Armadilha 1

Confiar só no erro médio global. Isso é a forma mais comum de aprovar surrogate ruim para optimização.

### Armadilha 2

Não validar ranking. Num GA, ranking errado pode ser pior do que erro absoluto moderado.

### Armadilha 3

Pular a sensibilidade local. Isso deixa passar modelos com superfície de resposta artificialmente irregular.

### Armadilha 4

Não fazer reavaliação dinâmica. O surrogate pode parecer bom no teste e ainda assim falhar quando guia a busca.

### Armadilha 5

Emitir uma aprovação genérica sem restrições explícitas. Isso cria excesso de confiança operacional.

## Checklist de implementação futura

- [ ] carregar bundles e registry do treino
- [ ] carregar splits e datasets corretos
- [ ] executar validação estática
- [ ] medir métricas globais por modo
- [ ] analisar top 10%
- [ ] correr sensibilidade local
- [ ] correr validação dinâmica ou alternativa equivalente
- [ ] gerar plots obrigatórios
- [ ] escrever métricas e tabelas auxiliares
- [ ] escrever `validation_decision.yaml`
- [ ] guardar log agregado

## Ligações

- [[BLUEPRINT_06_TRAIN_MODEL]]
- [[BLUEPRINT_08_EXPORT_SURROGATE]]
- [[BLUEPRINT_09_USE_IN_GA]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
