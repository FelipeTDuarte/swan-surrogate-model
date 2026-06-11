---
tags:
  - blueprint
  - export
  - surrogate
  - SWAN
  - GA
  - deployment
aliases:
  - Entrega 10 dos Blueprints
  - Blueprint Export Surrogate
created: 2026-05-16
status: entrega-10
---

# BLUEPRINT_08_EXPORT_SURROGATE

> Especificação operacional do ficheiro responsável por exportar o surrogate já validado como artefacto único, versionado e seguro para inferência, preservando contratos, scalers, bounds da fitness, metadados do dataset e diferenças entre os modos B e C.

## Objetivo do ficheiro

Este ficheiro transforma um modelo já treinado e validado num artefacto de inferência estável para uso posterior no GA e noutros fluxos controlados.

O seu papel não é treinar, não é validar novamente e não é calcular a fitness final dentro do otimizador. O seu papel é empacotar o surrogate com tudo o que ele precisa para ser usado de forma reproduzível e sem ambiguidades.

Sem esta etapa, o projeto fica dependente de ficheiros soltos, convenções implícitas e conhecimento manual sobre que scaler, que versão de dataset e que bounds estavam associados ao modelo.

## Lugar no pipeline

A sequência lógica relevante é esta:
1. `BLUEPRINT_07_VALIDATE_MODEL.md` decide se o modelo pode avançar
2. `BLUEPRINT_08_EXPORT_SURROGATE.md` empacota o modelo aprovado
3. `BLUEPRINT_09_USE_IN_GA.md` consome apenas o artefacto exportado

Se esta etapa falhar, a integração no GA fica frágil, porque cada uso do surrogate pode reconstruir contexto de forma diferente.

## Inputs esperados

### Input 1 — `config/problem.yaml`

O ficheiro deve ler, no mínimo:
- `problem_id`
- `n_wecs`
- `fitness.normalization`
- `fitness.p_total_bounds`
- `fitness.hra_bounds`
- `hra.mode`

### Input 2 — `config/paths.yaml`

O ficheiro deve usar:
- `models_dir`
- `reports_dir`
- `logs_dir`

### Input 3 — bundles do treino

O ficheiro deve consumir os bundles produzidos em `06_train_model.py`, incluindo:
- ficheiro do modelo
- scaler dos inputs
- ordem das features
- registry do treino
- métricas do treino

### Input 4 — decisão de validação

O ficheiro deve ler `validation_decision.yaml` e só exportar modelos aprovados ou aprovados com restrições explícitas.

### Input 5 — artefactos de dataset

O ficheiro deve reter referência ao `dataset_registry.yaml` e à versão do dataset usado no treino.

## Outputs produzidos

### Output principal do modo B

Ficheiro sugerido:

```text
models/exported/surrogate_B_vX.bundle
```

### Output principal do modo C

Ficheiro sugerido:

```text
models/exported/surrogate_C_vX.bundle
```

### Outputs auxiliares obrigatórios

1. `models/exported/export_registry.yaml`
2. `models/exported/surrogate_B_vX_manifest.yaml`
3. `models/exported/surrogate_C_vX_manifest.yaml`
4. `reports/export_report.md`
5. `reports/logs/08_export_surrogate.log`

## Função de cada output auxiliar

### `export_registry.yaml`

Guarda o registo de todos os artefactos exportados, as suas versões, decisões de validação associadas e os caminhos finais.

### `surrogate_*_manifest.yaml`

Define o contrato de inferência do bundle exportado.

### `export_report.md`

Resume o que foi exportado, com que restrições, e que artefactos dependem desse bundle.

## Regra central do ficheiro

Só modelos aprovados podem ser exportados. Um bundle exportado deve conter tudo o que é necessário para inferência segura e rastreável, sem depender de reconstrução implícita de contexto.

## Funções obrigatórias

O ficheiro deve conter, no mínimo, as seguintes funções ou equivalentes.

### 1. `load_training_bundle(mode)`

Carrega os artefactos produzidos no treino para o modo B ou C.

### 2. `load_validation_decision(mode)`

Lê a decisão final de validação e verifica se a exportação é permitida.

### 3. `build_export_manifest(mode)`

Monta o manifesto do bundle exportado.

### 4. `package_model_bundle(mode)`

Empacota modelo, scalers, bounds, metadados e contratos num único artefacto lógico.

### 5. `verify_export_bundle(mode)`

Executa validações mínimas no bundle final antes de o marcar como pronto.

### 6. `write_export_registry()`

Atualiza o registo global dos artefactos exportados.

### 7. `write_export_report()`

Gera o relatório resumido da exportação.

## Fluxo interno

### Etapa 1 — carregar artefactos e decisão

Ler bundles do treino, registry do treino, registry do dataset e decisão de validação.

### Etapa 2 — verificar elegibilidade

Confirmar que o modelo está `APPROVED` ou `APPROVED_WITH_RESTRICTIONS` e que as restrições podem ser representadas explicitamente no manifesto.

### Etapa 3 — montar bundle exportável

Empacotar:
- modelo
- scaler
- ordem das features
- bounds de normalização
- versão do dataset
- versão do problema
- modo de output
- restrições operacionais

### Etapa 4 — validar integridade do bundle

Executar checks mínimos de carregamento e inferência de teste.

### Etapa 5 — persistir bundle e manifestos

Escrever bundle, manifesto, registry e relatório.

## O que um bundle exportado deve conter

### Núcleo mínimo obrigatório

Cada bundle exportado deve conter ou referenciar de forma segura:
- ficheiro do modelo
- ficheiro do scaler
- lista ordenada das features de input
- contrato do modo (`B` ou `C`)
- versão do dataset
- `problem_id`
- `n_wecs`
- bounds da normalização da fitness
- informação sobre outputs esperados
- decisão de validação
- restrições de uso

### Regra importante

Não basta guardar o modelo serializado. O bundle tem de transportar também o contexto mínimo necessário para inferência correta.

## Contrato de inferência do modo B

### Inputs esperados

```text
[x1, y1, x2, y2, ..., xN, yN, Hs, Tp, Dir]
```

### Outputs esperados

O bundle B deve devolver pelo menos:
- `P_total_pred`
- `HRA_pred_vector`
- metadados de validade básica da inferência

### Forma de saída sugerida

```python
{
  "p_total": float,
  "hra": [float, ...],
  "mode": "B",
  "valid": True,
  "warnings": []
}
```

## Contrato de inferência do modo C

### Inputs esperados

O input do modo C é o mesmo vetor tabular do modo B.

### Outputs esperados

O bundle C deve devolver pelo menos:
- `P_total_pred`
- campo previsto de `Hs`
- metadados do grid
- metadados de validade básica da inferência

### Forma de saída sugerida

```python
{
  "p_total": float,
  "hs_field": "array_or_tensor",
  "grid_id": "...",
  "field_shape": [ny, nx],
  "mode": "C",
  "valid": True,
  "warnings": []
}
```

## Normalização da fitness

### Regra principal

A exportação deve preservar os bounds de normalização min-max usados na fitness, mas não deve misturar predição física com combinação final de pesos do GA.

### Consequência prática

O bundle pode expor utilitários para normalizar `P_total` e HRA para `[0.01, 1]`, mas a combinação com `alpha` e `beta` continua fora do bundle principal, no nível de integração com o GA.

### Artefactos obrigatórios

O bundle deve incluir:
- `p_total_bounds`
- `hra_bounds`
- nome da política de normalização

## Restrições e uso permitido

### Regra

Se a validação produziu restrições, elas têm de aparecer no manifesto exportado.

### Exemplos

- válido apenas para modo B
- válido apenas dentro de certo envelope operacional
- não usar para GA final sem rechecagem periódica

### Proibição

Não exportar modelo com restrições apenas no texto de um relatório. As restrições têm de acompanhar o bundle.

## Verificações mínimas do bundle

Antes de marcar o bundle como pronto, o script deve verificar:
- que o modelo carrega
- que o scaler carrega
- que a ordem das features existe
- que o número de features bate certo com `n_wecs`
- que os bounds de normalização existem
- que uma inferência de fumo com shape válido corre sem crash

## Contrato de `surrogate_*_manifest.yaml`

Cada manifesto deve guardar, no mínimo:

```yaml
export_version: "v1"
problem_id: "swan_surrogate_n28_v1"
mode: "B"
n_wecs: 28
dataset_version: "v1"
training_run_id: "train_B_v1"
validation_run_id: "val_B_v1"
decision: "APPROVED"
restrictions: []
input_features:
  - x1
  - y1
  - x2
  - y2
  - Hs
  - Tp
  - Dir
normalization:
  name: "minmax_0.01_1"
  p_total_bounds: [0.0, 1.0]
  hra_bounds: [0.0, 1.0]
artifacts:
  model_file: "..."
  scaler_file: "..."
```

## Política de versionamento

### Regra principal

Nova exportação implica nova versão sempre que mudar pelo menos um dos seguintes pontos:
- modelo treinado
- versão do dataset
- bounds da normalização
- contrato de output
- restrições da validação
- ordem ou definição das features

### Convenção sugerida

```text
surrogate_B_v1.bundle
surrogate_C_v1.bundle
```

## Compatibilidade futura

### Regra

O formato do bundle deve ser escolhido de forma a permitir carregamento estável em produção. Pode ser, por exemplo:
- diretório compactado com manifesto e ficheiros internos
- pickle controlado para B
- artefacto PyTorch acompanhado de manifesto para C

### Observação

O blueprint não fecha um único formato binário, mas fecha o contrato lógico do bundle.

## Logging

### Eventos mínimos a registar

- bundles de treino carregados
- decisão de validação lida
- início da exportação por modo
- validações do bundle
- artefactos escritos
- exportação concluída ou bloqueada

## Núcleo comum, modo B e modo C

### Núcleo comum

Versionamento, manifesto, preservação de bounds, validação de artefactos e registry pertencem ao núcleo comum.

### Diferença para B

O bundle B exporta um surrogate de saída escalar ou vetorial curta, mais leve e mais simples de integrar.

### Diferença para C

O bundle C exporta um surrogate com saída espacial e precisa de carregar metadados de grid e `field_shape` de forma explícita.

### Regra prática

Mesmo se o utilizador começar usando só B no GA, a exportação de C deve continuar disponível quando a trilha C for aprovada.

## Dependências

Este blueprint depende de:
- `BLUEPRINTS_INDEX.md`
- `BLUEPRINT_CONFIG_GLOBAL.md`
- `BLUEPRINT_06_TRAIN_MODEL.md`
- `BLUEPRINT_07_VALIDATE_MODEL.md`
- modelos aprovados e bundles de treino íntegros

## Critérios de aceite

Este blueprint só é considerado fechado se permitir implementar um script que:
- exporte apenas modelos aprovados
- produza um bundle autoexplicativo e rastreável
- preserve bounds, features, scaler e versões
- registe restrições operacionais no manifesto
- valide o bundle com um teste mínimo de carregamento e inferência
- escreva registry, manifestos e relatório

## Riscos e armadilhas

### Armadilha 1

Exportar só o ficheiro do modelo e esquecer o resto do contexto. Isso quebra a inferência assim que mudares de ambiente.

### Armadilha 2

Perder os bounds da normalização da fitness. Depois o GA usa escalas erradas sem perceber.

### Armadilha 3

Não transportar restrições de validação para o bundle. O utilizador final assume segurança que não existe.

### Armadilha 4

Misturar no mesmo bundle regras de exportação e lógica de fitness do GA. Isso aumenta acoplamento desnecessário.

### Armadilha 5

Não testar carregamento real do bundle antes de o marcar como exportado.

## Checklist de implementação futura

- [ ] carregar bundle do treino
- [ ] carregar decisão de validação
- [ ] bloquear exportação de modelos rejeitados
- [ ] montar manifesto do bundle
- [ ] empacotar modelo, scaler e metadados
- [ ] preservar bounds da normalização
- [ ] validar carregamento do bundle
- [ ] validar inferência de fumo
- [ ] escrever bundle exportado
- [ ] escrever manifestos e registry
- [ ] escrever relatório de exportação
- [ ] guardar log agregado

## Ligações

- [[BLUEPRINT_07_VALIDATE_MODEL]]
- [[BLUEPRINT_09_USE_IN_GA]]
- [[BLUEPRINT_TRACEABILITY]]
- [[BLUEPRINT_CONFIG_GLOBAL]]
- [[surrogate_swan_plano_v2_auditado]]
