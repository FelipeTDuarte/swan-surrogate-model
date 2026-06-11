---
tags:
  - blueprint
  - GA
  - integration
  - surrogate
  - SWAN
  - optimization
aliases:
  - Entrega 11 dos Blueprints
  - Blueprint Use In GA
created: 2026-05-16
status: entrega-11
---

# BLUEPRINT_09_USE_IN_GA

> Especificação operacional do ficheiro responsável por integrar o surrogate exportado no loop do Algoritmo Genético, mantendo as restrições geométricas como regra inegociável, usando a normalização correta da fitness e preservando a possibilidade de rechecagem periódica com SNL-SWAN real.

## Objetivo do ficheiro

Este ficheiro liga o surrogate ao processo real de optimização. O seu papel é receber indivíduos do GA, validar pré-condições de inferência, chamar o bundle exportado do surrogate, normalizar `P_total` e HRA para a fitness e devolver ao GA uma avaliação rápida e consistente.

O objetivo não é substituir o filtro geométrico do teu código atual, não é reconstruir o contexto do modelo exportado e não é reinterpretar outputs brutos do SWAN. O objetivo é fazer uso operacional seguro do surrogate dentro do loop do GA.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_08_EXPORT_SURROGATE.md` produz o artefacto exportado
2. `BLUEPRINT_09_USE_IN_GA.md` integra o artefacto no GA
3. o GA passa a usar o surrogate como motor rápido de avaliação, com checkpoints opcionais no SWAN real

Se esta etapa falhar, o projeto arrisca dois problemas sérios: quebrar a coerência geométrica entre GA e dataset, ou usar a normalização da fitness de forma diferente da que foi congelada no treino.

## Regra central do ficheiro

O teu código atual de restrições geométricas continua a ser a fonte de verdade para viabilidade do layout. O surrogate só pode ser chamado **depois** de o layout ser confirmado como válido.

Layouts inválidos não devem ser avaliados com “peso negativo” nem com penalização probabilística tardia. Devem ser rejeitados antes da inferência.

## Inputs esperados

### Input 1 — bundle exportado do surrogate

O ficheiro deve carregar:
- `surrogate_B_vX.bundle` ou `surrogate_C_vX.bundle`
- manifesto associado
- `export_registry.yaml`

### Input 2 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `fitness.normalization`
- `fitness.p_total_bounds`
- `fitness.hra_bounds`
- `hra.mode`

### Input 3 — layout proposto pelo GA

O layout deve entrar no contrato geométrico já conhecido do projeto, antes de qualquer previsão:

```python
layout.shape == (N, 2)
```

### Input 4 — estado ou conjunto de estados de mar

O GA pode fornecer:
- um único estado de mar
- uma lista de estados de mar ponderados
- um conjunto de estados reduzidos por clustering operacional

### Input 5 — pesos da fitness

O ficheiro deve receber, explicitamente:
- `alpha`
- `beta`

ou equivalente que defina a ponderação entre `P_total` e HRA.

## Outputs produzidos

### Output principal

A função principal deve devolver, no mínimo:

```python
{
  "fitness": float,
  "p_total": float,
  "hra": float | list[float],
  "valid": bool,
  "warnings": list,
  "mode": "B" | "C"
}
```

### Outputs auxiliares recomendados

1. log operacional do GA com surrogate
2. registo de inferências auditadas
3. registo de checkpoints reavaliados com SWAN real

Ficheiros sugeridos:

```text
reports/logs/09_use_in_ga.log
reports/ga_inference_audit.csv
reports/ga_recheck_swan.csv
```

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_exported_surrogate()`

Carrega o bundle exportado e valida o manifesto.

### 2. `validate_layout_before_inference(layout)`

Usa a fonte de verdade geométrica do GA para confirmar que o layout é admissível.

### 3. `canonicalize_layout(layout)`

Aplica a ordenação canónica antes de montar o vetor de input.

### 4. `build_feature_vector(layout, sea_state)`

Transforma layout e estado de mar no vetor de input esperado pelo surrogate.

### 5. `predict_surrogate(feature_vector)`

Executa inferência no bundle carregado.

### 6. `normalize_targets_for_fitness(p_total, hra)`

Aplica a normalização min-max para `[0.01, 1]` usando os bounds congelados.

### 7. `combine_fitness(p_norm, hra_norm, alpha, beta)`

Calcula a fitness final que será usada pelo GA.

### 8. `evaluate_individual(layout, sea_states, alpha, beta)`

Orquestra a avaliação completa de um indivíduo.

### 9. `run_periodic_swan_recheck(selected_layouts)`

Executa rechecagem periódica com o solver real em layouts estratégicos.

## Fluxo interno

### Etapa 1 — carregar o bundle uma vez

O surrogate deve ser carregado e validado uma única vez fora do loop principal do GA.

### Etapa 2 — receber um indivíduo candidato

O GA propõe um layout e, quando aplicável, um conjunto de estados de mar e respetivos pesos.

### Etapa 3 — validar geometria

Antes de qualquer inferência:
- confirmar shape correto
- confirmar `n_wecs`
- aplicar o validador geométrico principal

Se o layout for inválido, a inferência não acontece.

### Etapa 4 — aplicar ordenação canónica

Ordenar os WECs segundo a convenção do projeto.

### Etapa 5 — montar inputs e prever

Construir vetor de features e chamar o surrogate.

### Etapa 6 — normalizar outputs para a fitness

Aplicar min-max usando os bounds congelados do bundle.

### Etapa 7 — combinar fitness final

Combinar `P_total` e HRA com os pesos `alpha` e `beta`.

### Etapa 8 — auditoria e rechecagem opcional

Registar a inferência e, periodicamente, reavaliar layouts selecionados com SWAN real.

## Contrato do layout no GA

### Forma esperada

```python
layout.shape == (N, 2)
```

### Regras

- o layout entra bruto na avaliação
- a função aplica ordenação canónica internamente antes de inferir
- a validação geométrica deve acontecer antes da ordenação final entrar no surrogate

### Fonte de verdade

A função de validação geométrica deve reutilizar a tua lógica de produção, não um penalizador aproximado.

## Política de invalidez geométrica

### Regra obrigatória

Se o layout for inválido, a função de avaliação deve devolver estado inválido sem chamar o surrogate.

### Opções de resposta

O blueprint permite duas estratégias seguras:

#### Estratégia A

Devolver `valid=False` e deixar o GA tratar o indivíduo como inelegível.

#### Estratégia B

Devolver uma fitness sentinela extremamente má, mas só **depois** de confirmar que o GA trata esse retorno como exclusão efetiva e não como candidato probabilístico residual.

### Recomendação

Como já disseste que a penalização tardia é inaceitável neste contexto, a estratégia preferida aqui é exclusão operacional antes da inferência.

## Contrato dos estados de mar

### Caso simples

Se houver apenas um estado de mar:

```python
sea_state = [Hs, Tp, Dir]
```

### Caso composto

Se o indivíduo for avaliado sobre vários estados de mar ponderados, a função deve suportar batch interno e agregação externa.

### Regra

A agregação multiestado deve ser explícita e documentada. O blueprint não assume uma fórmula única, mas exige que essa fórmula esteja fechada no código do GA.

## Normalização da fitness

### Regra principal

`P_total` e HRA devem ser normalizados para `[0.01, 1]` **dentro da função de fitness**, usando os bounds congelados no bundle exportado.

### Regras específicas

- não recalcular bounds com base na população atual
- não usar min-max dinâmico por geração
- não usar bounds diferentes dos que acompanharam o treino/exportação

### Função de referência

```python
def minmax_01(x, xmin, xmax):
    if xmax == xmin:
        return 0.01
    z = (x - xmin) / (xmax - xmin)
    z = max(0.0, min(1.0, z))
    return 0.01 + 0.99 * z
```

## Combinação da fitness

### Regra

A fórmula exata deve ficar explícita no código do GA. O blueprint apenas fixa que a combinação acontece depois da normalização de `P_total` e HRA.

### Forma genérica sugerida

```python
fitness = alpha * p_norm + beta * hra_norm
```

### Observação

Se o modo B devolver múltiplas áreas de HRA, a regra de agregação entre áreas deve estar definida antes desta combinação.

## Uso do modo B

### Papel operacional

O modo B é o caminho mais simples e mais leve para integração direta no GA.

### Saída esperada

- `P_total`
- vetor HRA por área
- possibilidade de agregação para uma única fitness

### Regra prática

Se houver só uma área, o modo B cobre o antigo caso A como subconjunto direto.

## Uso do modo C

### Papel operacional

O modo C permite prever o campo completo de `Hs`, o que abre espaço para recalcular HRA depois e suportar análises mais flexíveis.

### Saída esperada

- `P_total`
- campo de `Hs`
- metadados de grid

### Regra prática

A integração no GA não deve obrigar o modo C a devolver o domínio inteiro como vetor achatado ao nível externo. O bundle pode devolver o campo e a função de integração extrai dele o HRA ou outro indicador relevante para a fitness.

## Predição vectorizada

### Recomendação forte

Se fores avaliar múltiplos estados de mar por indivíduo, a inferência deve acontecer em batch para reduzir overhead.

### Regra

O blueprint incentiva batch interno, mas a interface pública deve manter-se simples para o GA.

## Safety checks de inferência

### Antes da inferência

- bundle carregado corretamente
- modo correto selecionado
- número de features correto
- layout válido
- estado de mar dentro do envelope esperado ou com `WARNING`

### Depois da inferência

- `P_total` finito
- HRA finito no modo B
- campo e metadados coerentes no modo C
- ausência de shape incompatível

### Regra

Clipping silencioso não deve ser a solução principal. Se houver saída impossível, a inferência deve ser marcada para auditoria.

## Rechecagem periódica com SWAN real

### Objetivo

Evitar drift operacional e confirmar que o GA não está a explorar regiões onde o surrogate começa a falhar.

### Estratégia mínima

A cada bloco de gerações, selecionar alguns layouts relevantes e reavaliá-los com o SWAN real.

### Casos prioritários para rechecagem

- melhores indivíduos atuais
- layouts muito diferentes do histórico recente
- layouts com warnings do surrogate

### Saída mínima

Guardar comparação em `ga_recheck_swan.csv`.

## Auditoria de inferência

### Objetivo

Registar informação suficiente para rastrear decisões do GA sem criar overhead absurdo.

### Campos mínimos sugeridos

```text
timestamp, generation, individual_id, case_mode, valid, p_total_pred, hra_pred, p_norm, hra_norm, fitness, warnings
```

## Logging

### Eventos mínimos a registar

- bundle carregado
- erro de contrato do bundle
- layout inválido rejeitado
- warning de extrapolação de estado de mar
- falha de inferência
- rechecagem real executada

## Núcleo comum, modo B e modo C

### Núcleo comum

Validação geométrica, ordenação canónica, montagem de features, normalização, combinação da fitness, auditoria e rechecagem pertencem ao núcleo comum.

### Diferença para B

O modo B devolve targets escalares ou vetoriais curtos e é o candidato principal para integração imediata no GA.

### Diferença para C

O modo C devolve um campo espacial e exige uma etapa adicional de derivação do HRA ou outro indicador para a fitness.

### Regra prática

O GA deve poder escolher entre bundle B e bundle C sem mudar a sua lógica de restrições geométricas.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_08_EXPORT_SURROGATE.md`
- bundle exportado íntegro
- lógica geométrica do GA já validada

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um módulo que:
- carregue o surrogate uma vez fora do loop
- rejeite layouts inválidos antes da inferência
- monte features corretamente
- normalize `P_total` e HRA com bounds congelados
- devolva fitness pronta para o GA
- suporte batch multiestado quando necessário
- permita rechecagem periódica com SWAN real
- produza auditoria mínima das inferências

## Riscos e armadilhas

### Armadilha 1

Usar penalização tardia para layout inválido e ainda deixar o indivíduo entrar na seleção. Isso contradiz a regra do projeto.

### Armadilha 2

Recalcular min-max dentro de cada geração. Isso destrói a consistência da fitness.

### Armadilha 3

Não aplicar ordenação canónica antes da inferência. O mesmo layout físico passa a ter duas codificações possíveis.

### Armadilha 4

Misturar lógica de restrição geométrica com lógica do surrogate. Isso cria duplicação perigosa e fragilidade operacional.

### Armadilha 5

Não reavaliar periodicamente com SWAN real. O surrogate pode degradar-se exatamente nas regiões exploradas pelo GA.

## Checklist de implementação futura

- [ ] carregar bundle exportado
- [ ] validar manifesto do bundle
- [ ] ligar à fonte de verdade geométrica do GA
- [ ] rejeitar layouts inválidos antes da inferência
- [ ] aplicar ordenação canónica
- [ ] montar vetor de input
- [ ] prever surrogate
- [ ] normalizar `P_total` e HRA com bounds congelados
- [ ] combinar fitness com `alpha` e `beta`
- [ ] suportar batch multiestado
- [ ] guardar auditoria mínima
- [ ] implementar rechecagem periódica com SWAN real
- [ ] guardar log agregado

## Ligações

- [[BLUEPRINT_08_EXPORT_SURROGATE]]
- [[BLUEPRINT_TRACEABILITY]]
- [[BLUEPRINT_REVIEW_FINAL]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
