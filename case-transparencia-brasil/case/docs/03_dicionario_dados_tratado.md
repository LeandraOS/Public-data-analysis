# Dicionário da base tratada

Saída de `src/preparacao.preparar()` — **2.703 linhas** (2.706 brutas menos 3
versões antigas) × colunas abaixo. Persistida em
`data/processed/itens_compra_tratado.parquet` e `.csv.gz`.

Três colunas do arquivo original foram descartadas por não carregarem
informação: `nomeUnidadeMedida` (100% ausente), `codigoClasse` e `nomeClasse`
(constantes — são o recorte da extração, não variáveis).

## Em linguagem direta — as três coisas que você precisa saber antes de usar esta base

1. **Para qualquer estatística de preço, filtre `escopo_preco == "comparavel"`.**
   Sem esse filtro você estará somando preços de bisnaga com preços de
   comprimido e incluindo registros onde o valor do lote inteiro foi lançado
   como preço unitário. São 2.455 dos 2.703 registros.
2. **`valorTotalItem` é o valor homologado, não o valor pago.** Em registro de
   preços (89% da base), a ata registra o preço e a quantidade *máxima*; o
   empenho pode ser parcial ou não ocorrer. Não use como despesa efetiva.
3. **Para identificar fornecedor, use `niFornecedor` ou `raizCnpj` — nunca
   `nomeFornecedor`.** A mesma empresa aparece na fonte com até três razões
   sociais diferentes.

Dois campos merecem cautela adicional: `modalidadeDesc` e `criterioDesc` são
**hipóteses** decodificadas por evidência interna, não domínios documentados
pela fonte. E `marca` não deve ser usada como dimensão analítica: em 11,6% dos
casos ela não contém marca alguma.

---

**Origem:** `origem` = campo da fonte, apenas tipado e com sentinelas
normalizadas · `derivada` = criado nesta análise.

| Coluna | Tipo | Origem | Preenchidos | Distintos | Descrição e advertências |
|---|---|---|---|---|---|
| `idCompra` | string | origem | 2,703 (100.0%) | 1,578 | Identificador da compra. 1.578 compras, 1,71 itens em média. |
| `idItemCompra` | string | origem | 2,703 (100.0%) | 2,703 | **Chave primária.** Identificador técnico do item; único. |
| `forma` | string | origem | 2,703 (100.0%) | 2 | Sistema de preços: SISPP (praticados) ou SISRP (registro de preços). |
| `modalidade` | string | origem | 2,703 (100.0%) | 2 | Código da modalidade. `5` e `6`; leitura provável pregão/dispensa — **hipótese**, ver §5 das decisões. |
| `criterioJulgamento` | string | origem | 2,629 (97.3%) | 3 | `V` (menor preço) ou `D` (maior desconto) — decodificado por evidência. Nulo ⟺ modalidade 6. |
| `numeroItemCompra` | string | origem | 2,703 (100.0%) | 204 | Número sequencial do item na compra. Compõe a chave de negócio. |
| `descricaoItem` | string | origem | 2,703 (100.0%) | 3 | Descrição CATMAT. **Apenas 3 valores distintos** na base. |
| `codigoItemCatalogo` | string | origem | 2,703 (100.0%) | 3 | Código CATMAT: 267502 (AAS 100mg), 267503 (Ácido Fólico 5mg), 268370 (Aciclovir 200mg). |
| `siglaUnidadeMedida` | string | origem | 17 (0.6%) | 2 | Quase integralmente ausente (99,4%). Não utilizada. |
| `nomeUnidadeFornecimento` | string | origem | 2,646 (97.9%) | 6 | **Crítica para comparação de preços.** COMPRIMIDO, CÁPSULA, BISNAGA, FRASCO-AMPOLA, FRASCO, SACHÊ. Ausente em 57 registros. |
| `siglaUnidadeFornecimento` | string | origem | 2,646 (97.9%) | 6 | Abreviação da unidade de fornecimento. |
| `capacidadeUnidadeFornecimento` | Float64 | origem | 2,703 (100.0%) | 6 | 99,4% igual a zero — interpretado como não informado, não como zero. Não utilizada. |
| `quantidade` | Float64 | origem | 2,703 (100.0%) | 918 | Quantidade adquirida. 1 a 71 milhões. Nenhum valor excluído: extremos são legítimos. |
| `precoUnitario` | Float64 | origem | 2,703 (100.0%) | 144 | Preço por **unidade de fornecimento** — só comparável dentro da mesma unidade. |
| `percentualMaiorDesconto` | Float64 | origem | 2,703 (100.0%) | 11 | Maior desconto vs preço de referência. >0 apenas quando critério = `D` (10 registros). |
| `niFornecedor` | string | origem | 2,703 (100.0%) | 526 | CNPJ do fornecedor. **Todos os 526 válidos** (dígito verificador módulo 11). |
| `nomeFornecedor` | string | origem | 2,703 (100.0%) | 560 | Razão social como veio da fonte. 560 valores para 526 CNPJs — **não usar como identidade**. |
| `marca` | string | origem | 2,695 (99.7%) | 482 | Marca/laboratório. **11,6% não contém marca** — não usada como dimensão analítica. |
| `codigoUasg` | string | origem | 2,703 (100.0%) | 614 | Código da unidade gestora. Dependência funcional perfeita com nomeUasg. |
| `nomeUasg` | string | origem | 2,703 (100.0%) | 613 | Nome da unidade gestora beneficiada. |
| `codigoMunicipio` | string | derivada | 2,694 (99.7%) | 374 | Código IBGE de 7 dígitos, **reconstituído** do texto corrompido (`4.108.403,00`). Nulo em 9 registros (string `'nan'` na origem). |
| `municipio` | string | origem | 2,694 (99.7%) | 374 | Município do ente comprador. Ausente em 9 registros. |
| `estado` | string | origem | 2,703 (100.0%) | 27 | UF. 27 valores; 100% consistente com o prefixo IBGE. |
| `codigoOrgao` | string | origem | 2,703 (100.0%) | 375 | Código do órgão responsável. |
| `nomeOrgao` | string | origem | 2,703 (100.0%) | 375 | Nome do órgão responsável. |
| `poder` | string | origem | 2,698 (99.8%) | 2 | E (Executivo), L (Legislativo), J (Judiciário). Nulo em 5. |
| `esfera` | string | origem | 2,646 (97.9%) | 3 | F (Federal), E (Estadual), M (Municipal). Nulo em 57. |
| `dataCompra` | datetime64[us, UTC] | origem | 2,703 (100.0%) | 720 | Data da compra, em **UTC**. dez/2021 a jul/2025. |
| `dataHoraAtualizacaoCompra` | datetime64[us, UTC] | origem | 2,703 (100.0%) | 805 | Última atualização da compra, UTC. |
| `dataHoraAtualizacaoItem` | datetime64[us, UTC] | origem | 2,703 (100.0%) | 1,043 | **Campo de controle da coleta incremental** (Etapa 1) e da deduplicação. UTC. |
| `dataResultado` | datetime64[us, UTC] | origem | 2,703 (100.0%) | 717 | Data da homologação. Igual a dataCompra em 99% dos casos. |
| `dataHoraAtualizacaoUasg` | datetime64[us, UTC] | origem | 2,703 (100.0%) | 258 | Última atualização do cadastro da UASG. Vai até 2010 — não é data do fato. |
| `raizCnpj` | string | derivada | 2,703 (100.0%) | 511 | 8 primeiros dígitos do CNPJ = **grupo econômico**. 511 raízes para 526 CNPJs. Usar em análises de concentração. |
| `cnpjValido` | bool | derivada | 2,703 (100.0%) | 1 | Resultado da validação de dígito verificador. True em 100% dos registros. |
| `fornecedorCanonico` | string | derivada | 2,703 (100.0%) | 510 | Razão social do registro **mais recente** do CNPJ. Regra determinística; usar esta, não `nomeFornecedor`. |
| `fornecedorNormalizado` | str | derivada | 2,703 (100.0%) | 510 | `fornecedorCanonico` em forma canônica (maiúsculas, sem diacríticos nem pontuação). |
| `uasgNormalizada` | str | derivada | 2,703 (100.0%) | 613 | `nomeUasg` em forma canônica. |
| `marcaNormalizada` | str | derivada | 2,695 (99.7%) | 353 | `marca` em forma canônica. 501 valores crus → 380 normalizados. |
| `marcaInformativa` | boolean | derivada | 2,703 (100.0%) | 2 | False quando `marca` não identifica laboratório (genérico, unidade, texto de edital, resíduo de HTML). |
| `valorTotalItem` | Float64 | derivada | 2,703 (100.0%) | 1,254 | `quantidade × precoUnitario`. **Valor homologado, NÃO valor pago** — ver §12 das decisões. |
| `logPrecoUnitario` | Float64 | derivada | 2,703 (100.0%) | 144 | log natural do preço. Base da detecção de outliers e da regressão log-log. |
| `logQuantidade` | Float64 | derivada | 2,703 (100.0%) | 918 | log natural da quantidade. |
| `anoCompra` | int32 | derivada | 2,703 (100.0%) | 5 | Ano da compra. Usado como efeito fixo. |
| `mesCompra` | string | derivada | 2,703 (100.0%) | 44 | Ano-mês (`YYYY-MM`). |
| `trimestreCompra` | string | derivada | 2,703 (100.0%) | 16 | Ano-trimestre (`YYYYQn`). Granularidade recomendada para os indicadores. |
| `diasAteAtualizacao` | int64 | derivada | 2,703 (100.0%) | 23 | Dias entre a compra e sua última atualização. Mediana ~450 dias — a fonte retifica o passado. |
| `itensNaCompra` | Int64 | derivada | 2,703 (100.0%) | 7 | Nº de itens na mesma `idCompra`. 1 a 7. |
| `formaDesc` | str | derivada | 2,703 (100.0%) | 2 | Rótulo legível de `forma`. |
| `modalidadeDesc` | str | derivada | 2,703 (100.0%) | 2 | Rótulo legível de `modalidade` — **marcado como hipótese**. |
| `criterioDesc` | str | derivada | 2,703 (100.0%) | 4 | Rótulo legível de `criterioJulgamento` — **marcado como hipótese**. |
| `esferaDesc` | str | derivada | 2,703 (100.0%) | 4 | Rótulo legível de `esfera`; ausência vira 'Não informado'. |
| `poderDesc` | str | derivada | 2,703 (100.0%) | 3 | Rótulo legível de `poder`. |
| `ehConsorcio` | bool | derivada | 2,703 (100.0%) | 2 | True se a UASG é consórcio intermunicipal. 26 registros; pagam ~20% abaixo da mediana. |
| `escopo_preco` | object | derivada | 2,703 (100.0%) | 4 | **Campo de controle mais importante.** `comparavel` (2.455) · `preco_implausivel` (160) · `unidade_divergente` (84) · `criterio_desconto` (4). |

---

## Colunas de marcação (`flag_*`)

Uma coluna booleana por regra de qualidade (27 no total), com o
resultado da regra **por linha**. É o que torna cada exclusão auditável:
qualquer registro fora do escopo de preço pode ser rastreado até a regra
específica que o classificou.

| Coluna | Registros marcados |
|---|---|
| `flag_COMP-01` | 57 |
| `flag_COMP-02` | 57 |
| `flag_COMP-03` | 9 |
| `flag_COMP-04` | 74 |
| `flag_COMP-05` | 2,703 |
| `flag_UNIC-01` | 0 |
| `flag_UNIC-02` | 0 |
| `flag_UNIC-03` | 0 |
| `flag_VALD-01` | 0 |
| `flag_VALD-02` | 0 |
| `flag_VALD-03` | 0 |
| `flag_VALD-04` | 9 |
| `flag_VALD-05` | 0 |
| `flag_VALD-06` | 313 |
| `flag_VALD-07` | 102 |
| `flag_CONS-01` | 424 |
| `flag_CONS-02` | 306 |
| `flag_CONS-03` | 0 |
| `flag_CONS-04` | 0 |
| `flag_CONS-05` | 0 |
| `flag_CONS-06` | 13 |
| `flag_CONS-07` | 2 |
| `flag_CONS-08` | 27 |
| `flag_ACUR-01` | 178 |
| `flag_ACUR-02` | 13 |
| `flag_ACUR-03` | 2,686 |
| `flag_ATUAL-01` | 1,845 |

Catálogo completo das regras — dimensão, severidade e ação adotada — em
`outputs/relatorio_qualidade.csv` e na seção 2.5 do relatório.

---

## Como usar a base tratada

```python
import pandas as pd
df = pd.read_parquet("data/processed/itens_compra_tratado.parquet")

# Estatísticas de preço: SEMPRE filtrar o escopo comparável
dfp = df[df.escopo_preco == "comparavel"]

# Contagens, cobertura territorial, concentração: usar a base completa
df.groupby("estado").size()

# Identidade de fornecedor: usar niFornecedor ou raizCnpj, nunca nomeFornecedor
df.groupby("raizCnpj").valorTotalItem.sum()
```

**Três advertências que valem repetir:**

1. `valorTotalItem` é valor **homologado**, não pago.
2. `precoUnitario` só é comparável **dentro da mesma unidade de fornecimento**.
3. `modalidadeDesc` e `criterioDesc` são **hipóteses** inferidas por evidência
   interna, não domínios documentados.
